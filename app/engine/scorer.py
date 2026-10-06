"""Soma as regras e corta o score em 100.

Os limiares moram no YAML. Este módulo só aplica a desigualdade:
abaixo de approve_below aprova, no meio desafia, de deny_at_or_above para cima nega.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.engine.rules.card_testing import card_testing_reason
from app.engine.rules.geo_bin import geo_bin_reason
from app.engine.rules.velocity import Reason, velocity_reason
from app.engine.rules.zscore import zscore_reason
from app.engine.snapshot import Snapshot


def load_rules(path: str) -> dict:
    # yaml.load (sem safe) instancia objetos arbitrários a partir do arquivo.
    # O arquivo é nosso, mas o hábito certo é safe_load.
    with Path(path).open(encoding="utf-8") as handle:
        rules = yaml.safe_load(handle)
    approve = int(rules["thresholds"]["approve_below"])
    deny = int(rules["thresholds"]["deny_at_or_above"])
    if approve >= deny:
        raise RuntimeError("thresholds incoerentes: approve_below precisa ser menor que deny_at_or_above")
    return rules


def score(snapshot: Snapshot, rules: dict) -> tuple[str, int, list[Reason]]:
    reasons: list[Reason] = []
    for reason in (
        velocity_reason(snapshot, rules["velocity"]),
        card_testing_reason(snapshot, rules["card_testing"]),
        geo_bin_reason(snapshot, rules["geo_bin"]),
        zscore_reason(snapshot, rules["zscore"]),
    ):
        if reason is not None:
            reasons.append(reason)
    total = min(100, sum(item.weight for item in reasons))
    return decide(total, rules["thresholds"]), total, reasons


def decide(total: int, thresholds: dict) -> str:
    if total >= int(thresholds["deny_at_or_above"]):
        return "deny"
    if total >= int(thresholds["approve_below"]):
        return "challenge"
    return "approve"
