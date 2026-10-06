"""Uma regra dispara ou não. O peso, quando dispara, é o do YAML inteiro.

Não somamos meio-peso por condição: ou o controle acendeu, ou não.
O detalhe lista quais condições acenderam, para a decisão ser explicável.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.snapshot import Snapshot


@dataclass(frozen=True)
class Reason:
    rule: str
    weight: int
    detail: str

    def as_dict(self) -> dict:
        return {"rule": self.rule, "weight": self.weight, "detail": self.detail}


def velocity_reason(snapshot: Snapshot, rule: dict) -> Reason | None:
    tripped: list[str] = []
    max_cards = int(rule["max_distinct_cards_per_ip"])
    max_email = int(rule["max_attempts_per_email"])
    if snapshot.distinct_cards_ip >= max_cards:
        tripped.append(
            f"{snapshot.distinct_cards_ip} cartões distintos no IP na janela (máximo {max_cards})"
        )
    if snapshot.email_attempts >= max_email:
        tripped.append(
            f"{snapshot.email_attempts} tentativas do e-mail na janela (máximo {max_email})"
        )
    # Controle desligado: não olha o fingerprint global nem o BIN.
    # Trocar IP e e-mail zera as únicas chaves que essa passagem consulta.
    if not snapshot.naive_velocity:
        max_card = int(rule["max_attempts_per_card"])
        max_bin = int(rule["max_attempts_per_bin"])
        if snapshot.card_attempts >= max_card:
            tripped.append(
                f"{snapshot.card_attempts} tentativas do mesmo cartão na janela (máximo {max_card})"
            )
        if snapshot.bin_attempts >= max_bin:
            tripped.append(
                f"{snapshot.bin_attempts} tentativas do BIN na janela (máximo {max_bin})"
            )
    if not tripped:
        return None
    return Reason("velocity", int(rule["weight"]), "; ".join(tripped))
