"""Interruptor que desliga um controle.

NAIVE_MODE desliga todos. O header X-Naive-Controls desliga um só,
para o script mostrar o furo e, no request seguinte, a correção, sem
subir dois processos.

ALLOW_DEMO_HEADER precisa ser false fora do laboratório. Com ele ligado,
qualquer cliente desliga o controle que quiser.
"""

from __future__ import annotations

from starlette.requests import Request

from app.settings import Settings

CONTROLS = ("idempotency", "challenge", "velocity", "signals")


def naive_enabled(request: Request, settings: Settings, control: str) -> bool:
    if control not in CONTROLS:
        raise ValueError(f"controle desconhecido: {control}")
    if settings.naive_mode:
        return True
    if not settings.allow_demo_header:
        return False
    raw = request.headers.get("x-naive-controls", "")
    asked = {part.strip().lower() for part in raw.split(",") if part.strip()}
    if "all" in asked:
        return True
    return control in asked
