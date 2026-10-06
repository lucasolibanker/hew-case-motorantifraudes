"""Chamada ao mock do PSP.

Timeout curto: o antifraude não fica pendurado no adquirente. Se o mock
está fora, a decisão continua valendo e o campo psp diz unavailable.
"""

from __future__ import annotations

import httpx

from app.logging_setup import log
from app.settings import Settings


def notify_psp(
    settings: Settings,
    *,
    payment_id: str,
    amount_cents: int,
    currency: str,
    idempotency_key: str,
) -> bool:
    try:
        response = httpx.post(
            f"{settings.psp_base_url.rstrip('/')}/charge",
            json={
                "payment_id": payment_id,
                "amount_cents": amount_cents,
                "currency": currency,
                "idempotency_key": idempotency_key,
            },
            timeout=3.0,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        log.warning("psp indisponível payment_id=%s", payment_id)
        return False
