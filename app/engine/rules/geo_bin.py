"""País do BIN contra país do IP, mais e-mail descartável.

País desconhecido não dispara. É fail-open de propósito: um IP que não
está na tabela pequena do laboratório não vira challenge eterno. O custo
é um atacante em um IP sem cadastro passar desta regra. As outras continuam.
"""

from __future__ import annotations

from app.engine.rules.velocity import Reason
from app.engine.snapshot import Snapshot


def geo_bin_reason(snapshot: Snapshot, rule: dict) -> Reason | None:
    tripped: list[str] = []
    if (
        snapshot.ip_country
        and snapshot.bin_country
        and snapshot.ip_country != snapshot.bin_country
    ):
        tripped.append(f"país do BIN {snapshot.bin_country} diferente do país do IP {snapshot.ip_country}")
    if snapshot.disposable_email:
        tripped.append("domínio de e-mail descartável")
    if not tripped:
        return None
    return Reason("geo_bin", int(rule["weight"]), "; ".join(tripped))
