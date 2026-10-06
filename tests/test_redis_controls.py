import threading

import fakeredis
import pytest

from app.errors import AppError
from app.security.otp import check_otp, issue_otp
from app.security.rate_limit import RateLimiter
from app.storage.redis_store import RedisStore


@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)


def test_idempotencia_devolve_a_resposta_gravada(fake_redis):
    store = RedisStore(fake_redis)
    first = store.claim_idempotency("chave-1", "hash", naive=False, ttl_seconds=60, race_window_seconds=0)
    assert first.owner
    store.finish_idempotency("chave-1", "hash", {"id": "pag-1"}, 60)
    second = store.claim_idempotency("chave-1", "hash", naive=False, ttl_seconds=60, race_window_seconds=0)
    assert second.owner is False
    assert second.stored == {"id": "pag-1"}


def test_mesma_chave_com_outro_corpo_conflita(fake_redis):
    store = RedisStore(fake_redis)
    store.claim_idempotency("chave-2", "hash-a", naive=False, ttl_seconds=60, race_window_seconds=0)
    store.finish_idempotency("chave-2", "hash-a", {"id": "pag-2"}, 60)
    with pytest.raises(AppError) as caught:
        store.claim_idempotency("chave-2", "hash-b", naive=False, ttl_seconds=60, race_window_seconds=0)
    assert caught.value.status_code == 409


def test_set_nx_so_um_dono(fake_redis):
    store = RedisStore(fake_redis)
    results = []

    def run():
        results.append(
            store.claim_idempotency("chave-3", "hash", naive=False, ttl_seconds=60, race_window_seconds=0)
        )

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(item.owner for item in results) == 1


def test_ingenuo_dois_donos_na_corrida(fake_redis, monkeypatch):
    barrier = threading.Barrier(2)

    def _sleep(_seconds):
        barrier.wait(timeout=3)

    monkeypatch.setattr("app.storage.redis_store.time.sleep", _sleep)
    store = RedisStore(fake_redis)
    results = []

    def run():
        results.append(
            store.claim_idempotency("chave-4", "hash", naive=True, ttl_seconds=60, race_window_seconds=1)
        )

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(item.owner for item in results) == 2


def test_janela_deslizante_esquece_o_que_e_velho(fake_redis):
    import time

    store = RedisStore(fake_redis)
    store.redis.zadd("velocity:card:abc", {"velho": time.time() - 10_000})
    assert store.sliding_hit("velocity:card:abc", "novo", 600) == 1


def test_otp_uso_unico_e_teto_de_tentativas(fake_redis):
    code = issue_otp(fake_redis, "pag", "pepper", 60)
    assert check_otp(fake_redis, "pag", "000000", "pepper", 3).ok is False
    assert check_otp(fake_redis, "pag", code, "pepper", 3).ok is True
    assert check_otp(fake_redis, "pag", code, "pepper", 3).ok is False

    code = issue_otp(fake_redis, "pag-2", "pepper", 60)
    for _ in range(3):
        assert check_otp(fake_redis, "pag-2", "999999", "pepper", 3).ok is False
    assert check_otp(fake_redis, "pag-2", code, "pepper", 3).ok is False


def test_rate_limit(fake_redis):
    limiter = RateLimiter(fake_redis, max_hits=2, window_seconds=60)
    assert limiter.allow("203.0.113.10")
    assert limiter.allow("203.0.113.10")
    assert limiter.allow("203.0.113.10") is False
    assert limiter.allow("203.0.113.20") is True
