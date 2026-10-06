"""Postgres: histórico consultável.

O PAN em claro não tem coluna. O que dá para auditar é o HMAC, os últimos
4, o BIN derivado, o BIN que o cliente declarou e os dois IPs.

As queries usam parâmetro (%s). Concatenar customer_id na string abriria
SQL injection num campo que o cliente controla.
"""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.errors import AppError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY,
    amount_cents INTEGER NOT NULL,
    currency CHAR(3) NOT NULL,
    pan_hmac TEXT NOT NULL,
    pan_last4 CHAR(4) NOT NULL,
    bin CHAR(6) NOT NULL,
    client_bin CHAR(6) NOT NULL,
    customer_id TEXT NOT NULL,
    email TEXT NOT NULL,
    client_ip TEXT NOT NULL,
    observed_ip TEXT NOT NULL,
    client_country TEXT,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS payments_customer_idx ON payments (customer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS payments_idempotency_idx ON payments (idempotency_key);

CREATE TABLE IF NOT EXISTS decisions (
    id UUID PRIMARY KEY,
    payment_id UUID NOT NULL REFERENCES payments (id),
    decision TEXT NOT NULL,
    risk_score INTEGER NOT NULL,
    reasons JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS decisions_payment_idx ON decisions (payment_id, created_at);

CREATE TABLE IF NOT EXISTS webhook_events (
    event_id TEXT PRIMARY KEY,
    payment_id UUID,
    amount_cents INTEGER NOT NULL,
    status TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class Database:
    def __init__(self, url: str) -> None:
        self.url = url

    def init(self) -> None:
        statements = [part.strip() for part in _SCHEMA.split(";") if part.strip()]

        def _create(cur) -> None:
            for statement in statements:
                cur.execute(statement)

        self._run(_create)

    def insert_payment(self, row: dict[str, Any]) -> None:
        self._run(
            lambda cur: cur.execute(
                """
                INSERT INTO payments (
                    id, amount_cents, currency, pan_hmac, pan_last4, bin, client_bin,
                    customer_id, email, client_ip, observed_ip, client_country,
                    idempotency_key, status
                ) VALUES (
                    %(id)s, %(amount_cents)s, %(currency)s, %(pan_hmac)s, %(pan_last4)s,
                    %(bin)s, %(client_bin)s, %(customer_id)s, %(email)s, %(client_ip)s,
                    %(observed_ip)s, %(client_country)s, %(idempotency_key)s, %(status)s
                )
                """,
                row,
            )
        )

    def insert_decision(self, payment_id: str, decision: str, score: int, reasons: list[dict]) -> None:
        self._run(
            lambda cur: cur.execute(
                """
                INSERT INTO decisions (id, payment_id, decision, risk_score, reasons)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (str(uuid.uuid4()), payment_id, decision, score, Json(reasons)),
            )
        )

    def customer_amounts(self, customer_id: str, limit: int = 50) -> list[int]:
        def _query(cur) -> list[int]:
            cur.execute(
                """
                SELECT amount_cents FROM payments
                WHERE customer_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (customer_id, limit),
            )
            # Tentativas negadas entram na média. Se só contássemos capturas,
            # o fraudador apagaria da estatística tudo o que o motor barrou.
            return [int(row["amount_cents"]) for row in cur.fetchall()]

        return self._run(_query)

    def get_payment(self, payment_id: str) -> dict | None:
        try:
            uuid.UUID(payment_id)
        except ValueError:
            return None

        def _query(cur):
            cur.execute("SELECT * FROM payments WHERE id = %s", (payment_id,))
            row = cur.fetchone()
            return dict(row) if row else None

        return self._run(_query)

    def list_recent(self, limit: int = 50) -> list[dict]:
        def _query(cur):
            cur.execute(
                """
                SELECT p.*, d.decision, d.risk_score, d.reasons
                FROM payments p
                LEFT JOIN LATERAL (
                    SELECT decision, risk_score, reasons
                    FROM decisions
                    WHERE payment_id = p.id
                    ORDER BY created_at DESC
                    LIMIT 1
                ) d ON true
                ORDER BY p.created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

        return self._run(_query)

    def decisions_for(self, payment_id: str) -> list[dict]:
        def _query(cur):
            cur.execute(
                """
                SELECT decision, risk_score, reasons, created_at
                FROM decisions
                WHERE payment_id = %s
                ORDER BY created_at ASC
                """,
                (payment_id,),
            )
            return [dict(row) for row in cur.fetchall()]

        return self._run(_query)

    def set_status(self, payment_id: str, status: str) -> None:
        self._run(
            lambda cur: cur.execute(
                "UPDATE payments SET status = %s WHERE id = %s",
                (status, payment_id),
            )
        )

    def insert_webhook(self, event_id: str, payment_id: str | None, amount_cents: int, status: str) -> bool:
        """False se o event_id já estava na tabela (Redis pode ter sido esvaziado)."""

        def _query(cur) -> bool:
            cur.execute(
                """
                INSERT INTO webhook_events (event_id, payment_id, amount_cents, status)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (event_id, payment_id, amount_cents, status),
            )
            return cur.rowcount == 1

        return self._run(_query)

    def _run(self, fn):
        try:
            with psycopg.connect(self.url, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    return fn(cur)
        except psycopg.OperationalError as exc:
            raise AppError(503, "postgres indisponível") from exc
