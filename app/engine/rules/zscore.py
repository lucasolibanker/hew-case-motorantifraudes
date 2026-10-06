"""Z-score do valor contra o histórico do customer_id.

Cold start (poucas tentativas) contribui zero. Desvio zero também:
cinco compras iguais não têm escala para chamar a sexta de outlier.
Usa o desvio populacional das tentativas anteriores, sem incluir a atual,
senão o próprio outlier puxa a média e se esconde.
"""

from __future__ import annotations

import statistics

from app.engine.rules.velocity import Reason
from app.engine.snapshot import Snapshot


def zscore_reason(snapshot: Snapshot, rule: dict) -> Reason | None:
    history = snapshot.history_cents
    minimum = int(rule["min_history"])
    if len(history) < minimum:
        return None
    stdev = statistics.pstdev(history)
    if stdev == 0:
        return None
    mean = statistics.fmean(history)
    z_value = (snapshot.amount_cents - mean) / stdev
    threshold = float(rule["z_threshold"])
    if abs(z_value) < threshold:
        return None
    return Reason(
        "zscore",
        int(rule["weight"]),
        f"z={z_value:.2f} contra média {mean:.0f} e desvio {stdev:.0f} em {len(history)} tentativas",
    )
