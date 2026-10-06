"""Números que o motor lê. Quem preenche isto decide quais sinais são reais."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Snapshot:
    distinct_cards_ip: int
    email_attempts: int
    card_attempts: int
    bin_attempts: int
    low_amount_attempts: int
    distinct_cards_bin: int
    bin_samples: int
    bin_denies: int
    amount_cents: int
    ip_country: str | None
    bin_country: str | None
    disposable_email: bool
    history_cents: list[int]
    naive_velocity: bool
