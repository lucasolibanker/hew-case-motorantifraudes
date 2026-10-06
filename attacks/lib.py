"""Funções compartilhadas dos scripts.

O reset mexe no Redis e no Postgres publicados na máquina. Não existe
rota HTTP para apagar o cérebro do antifraude: quem roda o script já tem
a porta do laboratório.
"""

from __future__ import annotations

import os
import random
import sys
import time
import uuid
from pathlib import Path

import httpx
import psycopg
import redis

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)

from app.settings import get_settings  # noqa: E402

API = os.environ.get("API_URL", "http://localhost:8000")
PSP = os.environ.get("PSP_URL", "http://localhost:8001")


def show(title: str, attempt: str, response: httpx.Response) -> None:
    print(f"\n=== {title} ===", flush=True)
    print(f"tentativa: {attempt}", flush=True)
    print(f"resposta: HTTP {response.status_code} {response.text}", flush=True)


def reset_lab() -> None:
    settings = get_settings()
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2)
    client.flushdb()
    client.close()
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE webhook_events, decisions, payments")
    print("laboratório zerado (redis flushdb + truncate)")


def pan(bin6: str) -> str:
    tail = "".join(str(random.randint(0, 9)) for _ in range(10))
    return bin6 + tail


def payment_body(**overrides) -> dict:
    body = {
        "amount": "150.00",
        "currency": "BRL",
        "card": "4111111111111111",
        "bin": "411111",
        "customer_id": "cust_ok",
        "ip": "203.0.113.10",
        "email": "ana@example.com",
    }
    body.update(overrides)
    return body


def post_payment(body: dict, key: str | None = None, naive: str | None = None, timeout: float = 20) -> httpx.Response:
    headers = {"Idempotency-Key": key or str(uuid.uuid4())}
    if naive:
        headers["X-Naive-Controls"] = naive
    try:
        return httpx.post(f"{API}/payments", json=body, headers=headers, timeout=timeout)
    except httpx.ConnectError:
        print("API fora do ar. Na pasta Motor-antifraudes: docker compose up --build")
        raise SystemExit(2)


def post_json(path: str, body: dict, headers: dict | None = None) -> httpx.Response:
    try:
        return httpx.post(f"{API}{path}", json=body, headers=headers or {}, timeout=20)
    except httpx.ConnectError:
        print("API fora do ar. Na pasta Motor-antifraudes: docker compose up --build")
        raise SystemExit(2)


def wait_webhook(payment_id: str, seconds: float = 8) -> dict:
    deadline = time.time() + seconds
    while time.time() < deadline:
        response = httpx.get(f"{PSP}/sent-webhooks", params={"payment_id": payment_id}, timeout=5)
        items = response.json().get("items", [])
        if items:
            return items[-1]
        time.sleep(0.15)
    print("o mock não registrou webhook para", payment_id)
    raise SystemExit(1)


def charge_count(payment_ids: set[str]) -> int:
    total = 0
    for payment_id in payment_ids:
        response = httpx.get(f"{PSP}/charges", params={"payment_id": payment_id}, timeout=5)
        total += int(response.json()["count"])
    return total


def rules() -> dict:
    import yaml

    return yaml.safe_load((ROOT / "config" / "rules.yml").read_text(encoding="utf-8"))
