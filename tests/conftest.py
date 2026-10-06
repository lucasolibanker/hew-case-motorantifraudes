import fakeredis
import pytest


@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)
