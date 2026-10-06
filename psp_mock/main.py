"""Mock do adquirente.

Ele é burro de propósito. Um PSP de verdade também deduplicaria pela
Idempotency-Key. Se este mock deduplicasse, um gateway quebrado pareceria
seguro e o PoC da corrida não mostraria a segunda cobrança. A defesa tem
que estar no nosso serviço. O mock só registra cada chamada e devolve um
webhook assinado com o corpo exato que ele enviou.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
import uuid

import httpx
from fastapi import FastAPI

app = FastAPI(title="PSP mock")

_lock = threading.Lock()
_charges: list[dict] = []
_sent: list[dict] = []


def _secret() -> str:
    secret = os.environ.get("PSP_HMAC_SECRET", "")
    if not secret:
        raise RuntimeError("PSP_HMAC_SECRET ausente no mock")
    return secret


def _sign(secret: str, timestamp: str, raw: bytes) -> str:
    # Mesma construção da API: timestamp, ponto, corpo cru.
    message = timestamp.encode() + b"." + raw
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


@app.post("/charge")
def charge(payload: dict) -> dict:
    """Registra a cobrança e dispara o webhook em outra thread.

    A thread evita um deadlock: a API espera esta resposta, e o webhook
    volta para a API. Se o mock chamasse o webhook de forma síncrona no
    mesmo request, os dois ficariam parados um no outro.
    """
    record = {
        "payment_id": str(payload.get("payment_id", "")),
        "amount_cents": int(payload.get("amount_cents", 0)),
        "currency": str(payload.get("currency", "")),
        "idempotency_key": str(payload.get("idempotency_key", "")),
    }
    with _lock:
        _charges.append(record)

    def _send() -> None:
        body = {
            "event_id": f"evt_{uuid.uuid4().hex}",
            "payment_id": record["payment_id"],
            "amount_cents": record["amount_cents"],
            "currency": record["currency"],
            "status": "captured",
        }
        # Separadores fixos: o MAC é dos bytes, não da ideia do JSON.
        raw = json.dumps(body, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        signature = _sign(_secret(), timestamp, raw)
        item = {
            "payment_id": record["payment_id"],
            "timestamp": timestamp,
            "signature": signature,
            "body": raw.decode(),
        }
        with _lock:
            _sent.append(item)
        url = os.environ.get("WEBHOOK_URL", "")
        if not url:
            return
        try:
            httpx.post(
                url,
                content=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-PSP-Timestamp": timestamp,
                    "X-PSP-Signature": signature,
                },
                timeout=5.0,
            )
        except httpx.HTTPError:
            # A falha de entrega aparece como pagamento que não vira captured.
            return

    threading.Thread(target=_send, daemon=True).start()
    return {"status": "accepted"}


@app.get("/charges")
def charges(payment_id: str | None = None) -> dict:
    with _lock:
        items = list(_charges)
    if payment_id:
        items = [item for item in items if item["payment_id"] == payment_id]
    return {"count": len(items), "items": items}


@app.get("/sent-webhooks")
def sent_webhooks(payment_id: str | None = None) -> dict:
    """Devolve os bytes que o mock assinou, para o script de replay e tamper."""
    with _lock:
        items = list(_sent)
    if payment_id:
        items = [item for item in items if item["payment_id"] == payment_id]
    return {"count": len(items), "items": items}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
