"""POST /webhooks/psp.

O corpo é lido cru, antes de qualquer parse. O MAC é desses bytes.
Resserializar o JSON para "canonicalizar" quebraria a verificação: 10.0 e
10.00 são valores iguais e bytes diferentes. Por isso o webhook fala
amount_cents, um inteiro, e a gente não reescreve o corpo.

Ordem:
1. MAC e timestamp, com a mesma mensagem de erro para os dois.
2. JSON.
3. SET NX do event_id. Replay não chega na cobrança.
4. O pagamento precisa existir, estar approved ou verified, e o valor
   precisa ser o que autorizamos. Assinatura válida com outro amount
   não captura: o segredo do PSP pode vazar, o valor autorizado não muda.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Request

from app.errors import AppError
from app.logging_setup import log
from app.security.psp_signature import webhook_is_authentic
from app.storage.postgres import Database
from app.storage.redis_store import RedisStore

router = APIRouter()

_AUTH_DETAIL = "assinatura ou timestamp inválidos"


@router.post("/webhooks/psp")
async def psp_webhook(request: Request):
    settings = request.app.state.settings
    store: RedisStore = request.app.state.store
    db: Database = request.app.state.db
    raw = await request.body()
    timestamp = request.headers.get("x-psp-timestamp", "")
    signature = request.headers.get("x-psp-signature", "")
    if not webhook_is_authentic(
        secret=settings.psp_hmac_secret,
        timestamp=timestamp,
        raw_body=raw,
        signature=signature,
        tolerance_seconds=settings.webhook_tolerance_seconds,
    ):
        raise AppError(401, _AUTH_DETAIL)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(400, "corpo do webhook não é JSON") from exc

    event_id = str(payload.get("event_id") or "")
    payment_id = str(payload.get("payment_id") or "")
    if not event_id or not payment_id or "amount_cents" not in payload:
        raise AppError(400, "webhook sem event_id, payment_id ou amount_cents")
    try:
        uuid.UUID(payment_id)
    except ValueError as exc:
        raise AppError(400, "payment_id inválido") from exc
    try:
        amount_cents = int(payload["amount_cents"])
    except (TypeError, ValueError) as exc:
        raise AppError(400, "amount_cents inválido") from exc

    # Reserva depois da autenticação. Assinatura ruim não queima o event_id:
    # o PSP legítimo ainda pode reenviar o evento certo.
    first_time = store.claim_replay(event_id, settings.replay_ttl_seconds)
    if not first_time:
        raise AppError(409, "evento já processado")

    try:
        inserted = db.insert_webhook(event_id, payment_id, amount_cents, "received")
    except AppError:
        # O Redis já marcou o evento. Se o banco caiu, solta a marca
        # para o PSP conseguir reenviar quando o banco voltar.
        store.redis.delete(f"replay:{event_id}")
        raise
    if not inserted:
        raise AppError(409, "evento já processado")

    row = db.get_payment(payment_id)
    if row is None:
        raise AppError(404, "pagamento não encontrado")
    if row["status"] not in {"approved", "verified"}:
        raise AppError(409, "pagamento não está aguardando captura")
    if int(row["amount_cents"]) != amount_cents:
        raise AppError(409, "amount do webhook diferente do autorizado")

    db.set_status(payment_id, "captured")
    log.info("captura payment_id=%s event_id=%s", payment_id, event_id)
    return {"status": "captured"}
