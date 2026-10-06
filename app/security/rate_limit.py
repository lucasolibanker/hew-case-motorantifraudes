"""Rate limit por IP do socket.

A chave é o IP observado, não o IP do JSON. Se fosse o do JSON, o cliente
zeraria o limite a cada request.
"""

from __future__ import annotations


class RateLimiter:
    def __init__(self, redis, max_hits: int, window_seconds: int) -> None:
        self.redis = redis
        self.max_hits = max_hits
        self.window_seconds = window_seconds

    def allow(self, ip: str) -> bool:
        key = f"ratelimit:{ip}"
        count = int(self.redis.incr(key))
        if count == 1:
            # Primeira vez na janela: arma o TTL.
            # Se o processo morrer entre o INCR e o EXPIRE, a chave fica
            # sem TTL e o IP fica bloqueado para sempre. O ramo de baixo
            # conserta isso na próxima requisição.
            self.redis.expire(key, self.window_seconds)
        elif self.redis.ttl(key) < 0:
            self.redis.expire(key, self.window_seconds)
        return count <= self.max_hits
