"""Redis: idempotência, velocity, replay e rate limit.

Toda chave nasce com TTL. Sem TTL, um atacante enche a memória e o
antifraude cai — um jeito banal de furar o controle.

A janela de velocity é um sorted set: o score é o timestamp e membros
velhos saem com ZREMRANGEBYSCORE. Dois requests simultâneos podem os dois
passar um limiar por uma unidade (a trava atômica deste case é a
idempotência, não o contador). O comentário fica aqui para não parecer
que o ZSET resolve corrida.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass

from app.errors import AppError


@dataclass
class Claim:
    owner: bool
    stored: dict | None
    waiting: bool


@dataclass
class VelocityCounts:
    distinct_cards_ip: int
    email_attempts: int
    card_attempts: int
    bin_attempts: int
    low_amount_attempts: int
    distinct_cards_bin: int
    bin_samples: int
    bin_denies: int


class RedisStore:
    def __init__(self, redis) -> None:
        self.redis = redis

    def claim_idempotency(
        self,
        key: str,
        request_hash: str,
        *,
        naive: bool,
        ttl_seconds: int,
        race_window_seconds: float,
    ) -> Claim:
        """Reserva o direito de cobrar esta chave.

        Com a trava: SET NX. Só um request segue.
        Sem a trava: lê, espera, grava sem NX. Quem leu junto também segue.
        A espera existe para o script pegar as duas no meio. No uso real a
        janela é o tempo entre o GET e o SET, menor, mas existente sob carga.
        """
        result_key = f"idempotency:{key}"
        lock_key = f"idempotency:{key}:lock"
        stored = self._read_done(result_key, request_hash)
        if stored is not None:
            return Claim(owner=False, stored=stored, waiting=False)

        if naive:
            time.sleep(race_window_seconds)
            # Sem NX. O segundo SET só pisa no valor; os dois seguem como donos.
            self.redis.set(lock_key, request_hash, ex=30)
            return Claim(owner=True, stored=None, waiting=False)

        acquired = self.redis.set(lock_key, request_hash, nx=True, ex=30)
        if acquired:
            # Alguém pode ter gravado o resultado entre o GET e o SET NX
            # (a trava anterior expirou depois de uma resposta pronta).
            stored = self._read_done(result_key, request_hash)
            if stored is not None:
                self.redis.delete(lock_key)
                return Claim(owner=False, stored=stored, waiting=False)
            return Claim(owner=True, stored=None, waiting=False)

        current = self.redis.get(lock_key)
        if current is not None and current != request_hash:
            raise AppError(409, "Idempotency-Key reutilizada com outro corpo")
        return Claim(owner=False, stored=None, waiting=True)

    def wait_idempotency(self, key: str, request_hash: str, timeout_seconds: float = 8.0) -> dict:
        result_key = f"idempotency:{key}"
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            stored = self._read_done(result_key, request_hash)
            if stored is not None:
                return stored
            time.sleep(0.05)
        raise AppError(409, "pagamento com esta Idempotency-Key ainda em processamento")

    def finish_idempotency(self, key: str, request_hash: str, response: dict, ttl_seconds: int) -> None:
        payload = json.dumps({"status": "done", "request_hash": request_hash, "response": response})
        self.redis.set(f"idempotency:{key}", payload, ex=ttl_seconds)
        self.redis.delete(f"idempotency:{key}:lock")

    def release_lock(self, key: str) -> None:
        # Não apaga o resultado. Só solta a trava para um retry legítimo
        # quando o dono falhou antes de gravar a resposta.
        self.redis.delete(f"idempotency:{key}:lock")

    def _read_done(self, result_key: str, request_hash: str) -> dict | None:
        raw = self.redis.get(result_key)
        if not raw:
            return None
        data = json.loads(raw)
        if data.get("request_hash") != request_hash:
            raise AppError(409, "Idempotency-Key reutilizada com outro corpo")
        if data.get("status") != "done":
            return None
        return data["response"]

    def record_velocity(
        self,
        *,
        ip: str,
        email: str,
        card_fp: str,
        bin6: str,
        amount_cents: int,
        velocity_window: int,
        card_window: int,
        low_amount_cents: int,
    ) -> VelocityCounts:
        distinct_cards_ip = self.sliding_hit(f"velocity:ip:{ip}:cards", card_fp, velocity_window)
        email_attempts = self.sliding_hit(f"velocity:email:{email}", _unique(), velocity_window)
        card_attempts = self.sliding_hit(f"velocity:card:{card_fp}", _unique(), velocity_window)
        bin_attempts = self.sliding_hit(f"velocity:bin:{bin6}:attempts", _unique(), velocity_window)
        distinct_cards_bin = self.sliding_hit(f"velocity:bin:{bin6}:cards", card_fp, card_window)
        low_key = f"velocity:ip:{ip}:low"
        if amount_cents <= low_amount_cents:
            low_amount_attempts = self.sliding_hit(low_key, _unique(), card_window)
        else:
            low_amount_attempts = self.sliding_count(low_key, card_window)
        # A razão de negação olha o passado. A tentativa atual entra depois
        # da decisão, em record_outcome.
        bin_samples = self.sliding_count(f"outcomes:bin:{bin6}:attempts", card_window)
        bin_denies = self.sliding_count(f"outcomes:bin:{bin6}:denies", card_window)
        return VelocityCounts(
            distinct_cards_ip=distinct_cards_ip,
            email_attempts=email_attempts,
            card_attempts=card_attempts,
            bin_attempts=bin_attempts,
            low_amount_attempts=low_amount_attempts,
            distinct_cards_bin=distinct_cards_bin,
            bin_samples=bin_samples,
            bin_denies=bin_denies,
        )

    def record_outcome(self, bin6: str, denied: bool, window_seconds: int) -> None:
        self.sliding_hit(f"outcomes:bin:{bin6}:attempts", _unique(), window_seconds)
        if denied:
            self.sliding_hit(f"outcomes:bin:{bin6}:denies", _unique(), window_seconds)

    def claim_replay(self, event_id: str, ttl_seconds: int) -> bool:
        """True se este processo é o primeiro a ver o event_id."""
        return bool(self.redis.set(f"replay:{event_id}", "1", nx=True, ex=ttl_seconds))

    def sliding_hit(self, key: str, member: str, window_seconds: int) -> int:
        now = time.time()
        self.redis.zadd(key, {member: now})
        self.redis.zremrangebyscore(key, 0, now - window_seconds)
        count = int(self.redis.zcard(key))
        self.redis.expire(key, window_seconds)
        return count

    def sliding_count(self, key: str, window_seconds: int) -> int:
        now = time.time()
        self.redis.zremrangebyscore(key, 0, now - window_seconds)
        count = int(self.redis.zcard(key))
        if count:
            self.redis.expire(key, window_seconds)
        return count


def _unique() -> str:
    return uuid.uuid4().hex
