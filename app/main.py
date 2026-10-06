"""Aplicação. Sobe Redis, Postgres, regras e o rate limit.

O rate limit fica no middleware, na frente de todas as rotas menos /health.
/health fora do limite para o compose conseguir marcar a API como viva
mesmo quando um IP já estourou a janela.
"""

from __future__ import annotations

import redis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import dashboard, payments, webhooks
from app.engine.scorer import load_rules
from app.engine.tables import load_tables
from app.errors import AppError
from app.logging_setup import install_logging, log
from app.security.rate_limit import RateLimiter
from app.settings import get_settings
from app.storage.postgres import Database
from app.storage.redis_store import RedisStore

install_logging()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Antifraude H&W", version="1.0.0")
    app.state.settings = settings
    app.state.redis = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2)
    app.state.store = RedisStore(app.state.redis)
    app.state.db = Database(settings.database_url)
    app.state.rules = load_rules(settings.rules_path)
    app.state.tables = load_tables(
        settings.bins_path,
        settings.ip_countries_path,
        settings.disposable_emails_path,
        settings.lab_local_country,
    )
    app.state.limiter = RateLimiter(
        app.state.redis,
        settings.rate_limit_max,
        settings.rate_limit_window_seconds,
    )

    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.middleware("http")
    async def _rate_limit(request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        try:
            allowed = app.state.limiter.allow(ip)
        except redis.RedisError:
            log.warning("redis indisponível no rate limit")
            return JSONResponse(status_code=503, content={"detail": "redis indisponível"})
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "rate limit excedido"},
                headers={"Retry-After": str(settings.rate_limit_window_seconds)},
            )
        return await call_next(request)

    @app.on_event("startup")
    def _startup() -> None:
        app.state.redis.ping()
        app.state.db.init()
        if settings.naive_mode or settings.allow_demo_header or settings.expose_otp:
            log.warning(
                "modo de laboratório naive_mode=%s allow_demo_header=%s expose_otp=%s",
                settings.naive_mode,
                settings.allow_demo_header,
                settings.expose_otp,
            )

    @app.get("/health")
    def health() -> dict:
        app.state.redis.ping()
        app.state.db._run(lambda cur: cur.execute("SELECT 1"))
        return {"status": "ok"}

    app.include_router(payments.router)
    app.include_router(webhooks.router)
    app.include_router(dashboard.router)
    return app


app = create_app()
