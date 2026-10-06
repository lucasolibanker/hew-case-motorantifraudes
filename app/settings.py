"""Configuração lida do ambiente.

Nada de segredo com default silencioso: se PSP_HMAC_SECRET ou PAN_PEPPER
faltarem, o processo não sobe. Falhar no boot é melhor do que assinar
webhook com string vazia e aceitar qualquer corpo.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    psp_hmac_secret: str
    pan_pepper: str

    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql://antifraud:antifraud@localhost:5433/antifraud"
    psp_base_url: str = "http://localhost:8001"

    rules_path: str = "config/rules.yml"
    bins_path: str = "config/bins.csv"
    ip_countries_path: str = "config/ip_countries.csv"
    disposable_emails_path: str = "config/disposable_domains.txt"

    naive_mode: bool = False
    allow_demo_header: bool = True
    expose_otp: bool = True

    idempotency_ttl_seconds: int = 86400
    webhook_tolerance_seconds: int = 300
    replay_ttl_seconds: int = 86400
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 3
    naive_race_window_ms: int = 250

    rate_limit_max: int = 300
    rate_limit_window_seconds: int = 60
    lab_local_country: str = "BR"


@lru_cache
def get_settings() -> Settings:
    return Settings()
