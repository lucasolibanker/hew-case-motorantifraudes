"""OTP do step-up.

O código em claro volta para o chamador (e, no laboratório, para o JSON).
No Redis fica só o HMAC. A comparação é em tempo constante, com teto de
tentativas e uso único.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass

from app.errors import AppError


@dataclass
class OtpResult:
    ok: bool
    detail: str


def _digest(pepper: str, payment_id: str, code: str) -> str:
    # Prefixo "otp:" para este HMAC não ser intercambiável com o do PAN,
    # mesmo os dois usando o pepper.
    material = f"otp:{payment_id}:{code}".encode()
    return hmac.new(pepper.encode(), material, hashlib.sha256).hexdigest()


def issue_otp(redis, payment_id: str, pepper: str, ttl_seconds: int) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    payload = json.dumps({"digest": _digest(pepper, payment_id, code), "attempts": 0})
    redis.set(_key(payment_id), payload, ex=ttl_seconds)
    return code


def _key(payment_id: str) -> str:
    return f"otp:{payment_id}"


def check_otp(
    redis,
    payment_id: str,
    code: str,
    pepper: str,
    max_attempts: int,
) -> OtpResult:
    key = _key(payment_id)
    raw = redis.get(key)
    if not raw:
        # Compara dois digests iguais só para não retornar mais rápido
        # quando a chave não existe. O ganho é pequeno; o hábito importa.
        dummy = _digest(pepper, payment_id, "000000")
        hmac.compare_digest(dummy, dummy)
        return OtpResult(False, "OTP expirado ou ausente")

    data = json.loads(raw)
    if int(data["attempts"]) >= max_attempts:
        return OtpResult(False, "OTP bloqueado por excesso de tentativas")

    presented = _digest(pepper, payment_id, code)
    if not hmac.compare_digest(presented, data["digest"]):
        data["attempts"] = int(data["attempts"]) + 1
        # Preserva o TTL. SET com EX novo empurraria a expiração para frente
        # e o atacante renovaria a janela a cada chute.
        remaining = int(redis.ttl(key))
        redis.set(key, json.dumps(data), ex=remaining if remaining > 0 else 1)
        return OtpResult(False, "OTP inválido")

    redis.delete(key)
    return OtpResult(True, "OTP aceito")


def discard_otp(redis, payment_id: str) -> None:
    redis.delete(_key(payment_id))


def require_code_shape(code: str) -> None:
    if not code or len(code) > 12:
        raise AppError(400, "código ausente")
