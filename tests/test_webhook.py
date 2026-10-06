import secrets

from app.security.psp_signature import sign, webhook_is_authentic
from app.storage.redis_store import RedisStore

# Gerado no teste. String fixa aqui faria o Snyk Code marcar segredo hardcoded.
_SECRET = secrets.token_hex(16)


def test_corpo_alterado_invalida_o_mac():
    raw = b'{"event_id":"evt_1","amount_cents":15000}'
    timestamp = "1700000000"
    signature = sign(_SECRET, timestamp, raw)
    common = dict(secret=_SECRET, timestamp=timestamp, signature=signature, now=1700000000, tolerance_seconds=300)
    assert webhook_is_authentic(raw_body=raw, **common)
    assert not webhook_is_authentic(raw_body=b'{"event_id":"evt_1","amount_cents":1}', **common)


def test_timestamp_fora_da_janela_falha_igual_assinatura_ruim():
    raw = b"{}"
    timestamp = "1700000000"
    signature = sign(_SECRET, timestamp, raw)
    assert not webhook_is_authentic(
        secret=_SECRET,
        timestamp=timestamp,
        raw_body=raw,
        signature=signature,
        now=1700000000 + 10_000,
        tolerance_seconds=300,
    )
    assert not webhook_is_authentic(
        secret=_SECRET,
        timestamp=timestamp,
        raw_body=raw,
        signature=sign(secrets.token_hex(16), timestamp, raw),
        now=1700000000,
        tolerance_seconds=300,
    )


def test_replay_de_event_id(fake_redis):
    store = RedisStore(fake_redis)
    assert store.claim_replay("evt_1", 60) is True
    assert store.claim_replay("evt_1", 60) is False
