"""POST /payments, GET /payments/{id} e POST /payments/{id}/verify.

Ordem do POST, de propósito:
1. A chave de idempotência é obrigatória antes de qualquer efeito.
2. O PAN vira HMAC aqui. Daqui para baixo o número não existe.
3. A reserva da chave acontece antes do score. Replay não incrementa velocity.
4. approve é o único estado que chama o PSP neste endpoint.
5. challenge guarda OTP e espera /verify. deny para.
6. A resposta pronta é gravada no Redis. A próxima chamada com a mesma
   chave devolve este JSON, sem segunda cobrança.

Janela que ainda existe, e o README assume: se o processo morre depois de
chamar o PSP e antes de gravar a resposta, um retry pode cobrar de novo.
O SET NX fecha a corrida entre dois requests vivos. Não fecha um crash
no meio. Em produção a trava e a cobrança no adquirente compartilhariam
a mesma chave, e o PSP também deduplicaria.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid

from fastapi import APIRouter, Request

from app.engine.scorer import score
from app.engine.signals import resolve_signals
from app.engine.snapshot import Snapshot
from app.errors import AppError
from app.logging_setup import log
from app.models import PaymentIn, PaymentOut, PaymentState, ReasonOut, VerifyIn
from app.money import from_cents, to_cents
from app.psp_client import notify_psp
from app.security.naive import naive_enabled
from app.security.otp import check_otp, discard_otp, issue_otp, require_code_shape
from app.security.pan import fingerprint, last4
from app.storage.postgres import Database
from app.storage.redis_store import RedisStore

router = APIRouter()

_IDEMPOTENCY = re.compile(r"^[A-Za-z0-9._:-]{8,200}$")


def _idempotency_key(request: Request) -> str:
    key = request.headers.get("idempotency-key", "").strip()
    if not _IDEMPOTENCY.fullmatch(key):
        raise AppError(400, "Idempotency-Key é obrigatória e deve ter entre 8 e 200 caracteres seguros")
    return key


def _request_hash(payload: PaymentIn) -> str:
    # sort_keys: a mesma compra com os campos em outra ordem é a mesma compra.
    raw = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _observed_ip(request: Request) -> str:
    # Não lemos X-Forwarded-For. Sem uma lista de proxies confiáveis, esse
    # header é só mais um campo que o cliente escreve.
    if request.client is None:
        return "0.0.0.0"
    return request.client.host


@router.post("/payments")
def create_payment(request: Request, payload: PaymentIn):
    settings = request.app.state.settings
    store: RedisStore = request.app.state.store
    db: Database = request.app.state.db
    rules = request.app.state.rules
    tables = request.app.state.tables

    key = _idempotency_key(request)
    request_hash = _request_hash(payload)
    naive_idempotency = naive_enabled(request, settings, "idempotency")
    naive_velocity = naive_enabled(request, settings, "velocity")
    naive_signals = naive_enabled(request, settings, "signals")
    observed_ip = _observed_ip(request)
    signals = resolve_signals(
        payload,
        observed_ip,
        tables,
        naive_signals=naive_signals,
        naive_velocity=naive_velocity,
    )
    pan_fp = fingerprint(payload.card, settings.pan_pepper)
    amount_cents = to_cents(payload.amount)

    owner = False
    finished = False
    try:
        claim = store.claim_idempotency(
            key,
            request_hash,
            naive=naive_idempotency,
            ttl_seconds=settings.idempotency_ttl_seconds,
            race_window_seconds=settings.naive_race_window_ms / 1000,
        )
        if not claim.owner:
            if claim.stored is not None:
                return claim.stored
            return store.wait_idempotency(key, request_hash)

        owner = True
        counts = store.record_velocity(
            ip=signals.scoring_ip,
            email=payload.email,
            card_fp=pan_fp,
            bin6=signals.scoring_bin,
            amount_cents=amount_cents,
            velocity_window=int(rules["velocity"]["window_seconds"]),
            card_window=int(rules["card_testing"]["window_seconds"]),
            low_amount_cents=int(rules["card_testing"]["low_amount_cents"]),
        )
        history = db.customer_amounts(payload.customer_id)
        snapshot = Snapshot(
            distinct_cards_ip=counts.distinct_cards_ip,
            email_attempts=counts.email_attempts,
            card_attempts=counts.card_attempts,
            bin_attempts=counts.bin_attempts,
            low_amount_attempts=counts.low_amount_attempts,
            distinct_cards_bin=counts.distinct_cards_bin,
            bin_samples=counts.bin_samples,
            bin_denies=counts.bin_denies,
            amount_cents=amount_cents,
            ip_country=signals.ip_country,
            bin_country=signals.bin_country,
            disposable_email=signals.disposable_email,
            history_cents=history,
            naive_velocity=naive_velocity,
        )
        decision, total, reasons = score(snapshot, rules)
        payment_id = str(uuid.uuid4())
        status = {"approve": "approved", "challenge": "challenged", "deny": "denied"}[decision]
        db.insert_payment(
            {
                "id": payment_id,
                "amount_cents": amount_cents,
                "currency": payload.currency,
                "pan_hmac": pan_fp,
                "pan_last4": last4(payload.card),
                "bin": payload.card[:6],
                "client_bin": payload.bin,
                "customer_id": payload.customer_id,
                "email": payload.email,
                "client_ip": payload.ip,
                "observed_ip": observed_ip,
                "client_country": payload.country,
                "idempotency_key": key,
                "status": status,
            }
        )
        reason_dicts = [item.as_dict() for item in reasons]
        db.insert_decision(payment_id, decision, total, reason_dicts)
        store.record_outcome(
            signals.scoring_bin,
            decision == "deny",
            int(rules["card_testing"]["window_seconds"]),
        )

        psp_state = "skipped"
        otp_demo = None
        if decision == "approve":
            called = notify_psp(
                settings,
                payment_id=payment_id,
                amount_cents=amount_cents,
                currency=payload.currency,
                idempotency_key=key,
            )
            psp_state = "called" if called else "unavailable"
        elif decision == "challenge":
            code = issue_otp(
                store.redis,
                payment_id,
                settings.pan_pepper,
                settings.otp_ttl_seconds,
            )
            if settings.expose_otp:
                otp_demo = code

        body = PaymentOut(
            id=payment_id,
            amount=from_cents(amount_cents),
            currency=payload.currency,
            decision=decision,
            risk_score=total,
            reasons=[ReasonOut(**item) for item in reason_dicts],
            status=status,
            psp=psp_state,
            otp_demo=otp_demo,
        ).model_dump(exclude_none=True)
        store.finish_idempotency(key, request_hash, body, settings.idempotency_ttl_seconds)
        finished = True
        # Sem PAN, sem e-mail. O id basta para achar a linha no Postgres.
        log.info("decisão payment_id=%s score=%s decision=%s", payment_id, total, decision)
        return body
    except Exception:
        if owner and not finished:
            store.release_lock(key)
        raise


@router.get("/payments/{payment_id}", response_model=PaymentState)
def get_payment(payment_id: str, request: Request) -> PaymentState:
    db: Database = request.app.state.db
    row = db.get_payment(payment_id)
    if row is None:
        raise AppError(404, "pagamento não encontrado")
    decisions = []
    for item in db.decisions_for(payment_id):
        reasons = item["reasons"] or []
        decisions.append(
            {
                "decision": item["decision"],
                "risk_score": int(item["risk_score"]),
                "reasons": reasons,
                "created_at": item["created_at"].isoformat(),
            }
        )
    return PaymentState(
        id=str(row["id"]),
        status=row["status"],
        amount=from_cents(int(row["amount_cents"])),
        currency=row["currency"].strip(),
        pan_last4=row["pan_last4"],
        customer_id=row["customer_id"],
        email=row["email"],
        observed_ip=row["observed_ip"],
        client_ip=row["client_ip"],
        bin=row["bin"],
        client_bin=row["client_bin"],
        client_country=row["client_country"],
        decisions=decisions,
    )


@router.post("/payments/{payment_id}/verify")
def verify_payment(payment_id: str, payload: VerifyIn, request: Request):
    """Step-up.

    Endurecido: só sai de challenged com o OTP certo, uma vez.
    Ingênuo: qualquer código serve, e repetir a chamada cobra de novo.
    Os dois olham o mesmo endpoint. O que muda é o interruptor.
    """
    settings = request.app.state.settings
    store: RedisStore = request.app.state.store
    db: Database = request.app.state.db
    require_code_shape(payload.code)
    row = db.get_payment(payment_id)
    if row is None:
        raise AppError(404, "pagamento não encontrado")
    status = row["status"]
    if status == "denied":
        raise AppError(409, "pagamento negado não aceita verificação")

    naive = naive_enabled(request, settings, "challenge")
    if naive:
        if status not in {"challenged", "verified", "approved", "captured"}:
            raise AppError(409, "pagamento não está em challenge")
        # Não consulta o digest. Não consome tentativa. Chama o PSP de novo.
        discard_otp(store.redis, payment_id)
        db.set_status(payment_id, "verified")
        previous = db.decisions_for(payment_id)
        previous_score = int(previous[-1]["risk_score"]) if previous else 0
        db.insert_decision(
            payment_id,
            "approve",
            previous_score,
            [{"rule": "step_up", "weight": 0, "detail": "verificação aceita com o controle desligado, sem validar o OTP"}],
        )
        called = notify_psp(
            settings,
            payment_id=payment_id,
            amount_cents=int(row["amount_cents"]),
            currency=row["currency"].strip(),
            idempotency_key=row["idempotency_key"],
        )
        log.info("verify sem controle payment_id=%s", payment_id)
        return {"id": payment_id, "status": "verified", "psp": "called" if called else "unavailable"}

    if status != "challenged":
        raise AppError(409, "pagamento não está aguardando verificação")
    result = check_otp(
        store.redis,
        payment_id,
        payload.code,
        settings.pan_pepper,
        settings.otp_max_attempts,
    )
    if not result.ok:
        raise AppError(401, result.detail)
    db.set_status(payment_id, "verified")
    previous = db.decisions_for(payment_id)
    previous_score = int(previous[-1]["risk_score"]) if previous else 0
    db.insert_decision(
        payment_id,
        "approve",
        previous_score,
        [{"rule": "step_up", "weight": 0, "detail": "OTP aceito"}],
    )
    called = notify_psp(
        settings,
        payment_id=payment_id,
        amount_cents=int(row["amount_cents"]),
        currency=row["currency"].strip(),
        idempotency_key=row["idempotency_key"],
    )
    log.info("verify ok payment_id=%s", payment_id)
    return {"id": payment_id, "status": "verified", "psp": "called" if called else "unavailable"}
