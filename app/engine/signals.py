"""Fronteira entre o que o cliente afirma e o que o servidor observa.

A evasão de sinais forjados mora aqui, não na comparação de países.
A comparação é honesta. O buraco é alimentar essa comparação com o IP,
o BIN e o país que vieram no JSON.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.tables import Tables
from app.models import PaymentIn


@dataclass(frozen=True)
class ResolvedSignals:
    scoring_ip: str
    scoring_bin: str
    ip_country: str | None
    bin_country: str | None
    disposable_email: bool


def resolve_signals(
    payload: PaymentIn,
    observed_ip: str,
    tables: Tables,
    *,
    naive_signals: bool,
    naive_velocity: bool,
) -> ResolvedSignals:
    # Velocity ingênuo também chaveia pelo IP do JSON. Se usássemos o IP do
    # socket, trocar o campo `ip` não escaparia do contador por IP — e o
    # PoC de estilhaçar velocity não teria o que mostrar. O contador global
    # do cartão é a correção quando o IP de origem é realmente outro.
    trust_client_ip = naive_signals or naive_velocity
    scoring_ip = payload.ip if trust_client_ip else observed_ip
    scoring_bin = payload.bin if naive_signals else payload.card[:6]

    if naive_signals and payload.country:
        # O cliente escolheu o país. A tabela de IP nem é consultada.
        ip_country = payload.country
    else:
        ip_country = tables.country_for_ip(scoring_ip)

    # E-mail descartável só pesa na versão endurecida. Na ingênua, o
    # atacante abre caixa em mailinator e o motor trata como cliente novo.
    disposable = False if naive_signals else tables.is_disposable(payload.email)
    return ResolvedSignals(
        scoring_ip=scoring_ip,
        scoring_bin=scoring_bin,
        ip_country=ip_country,
        bin_country=tables.country_for_bin(scoring_bin),
        disposable_email=disposable,
    )
