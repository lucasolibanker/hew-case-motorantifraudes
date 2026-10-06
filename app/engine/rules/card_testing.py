"""Card testing: valor baixo, muitos cartões no mesmo BIN, ou BIN que já falha muito.

A razão de negação usa só o histórico. A tentativa que está sendo julgada
ainda não entrou no denominador, senão ela diluiria a própria suspeita.
"""

from __future__ import annotations

from app.engine.rules.velocity import Reason
from app.engine.snapshot import Snapshot


def card_testing_reason(snapshot: Snapshot, rule: dict) -> Reason | None:
    tripped: list[str] = []
    low_max = int(rule["max_low_amount_attempts"])
    cards_max = int(rule["max_distinct_cards_per_bin"])
    if snapshot.low_amount_attempts >= low_max:
        tripped.append(
            f"{snapshot.low_amount_attempts} tentativas de valor baixo no IP (máximo {low_max})"
        )
    if snapshot.distinct_cards_bin >= cards_max:
        tripped.append(
            f"{snapshot.distinct_cards_bin} cartões distintos no BIN (máximo {cards_max})"
        )
    samples = snapshot.bin_samples
    minimum = int(rule["min_samples_for_ratio"])
    if samples >= minimum:
        ratio = snapshot.bin_denies / samples
        limit = float(rule["max_deny_ratio"])
        if ratio >= limit:
            tripped.append(
                f"taxa de negação do BIN em {ratio:.0%} com {samples} amostras (máximo {limit:.0%})"
            )
    if not tripped:
        return None
    return Reason("card_testing", int(rule["weight"]), "; ".join(tripped))
