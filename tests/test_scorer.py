import pytest

from app.engine.scorer import decide, load_rules, score
from app.engine.signals import resolve_signals
from app.engine.snapshot import Snapshot
from app.engine.tables import load_tables
from app.models import PaymentIn


@pytest.fixture(scope="module")
def rules():
    return load_rules("config/rules.yml")


def _snapshot(**overrides) -> Snapshot:
    base = dict(
        distinct_cards_ip=1,
        email_attempts=1,
        card_attempts=1,
        bin_attempts=1,
        low_amount_attempts=0,
        distinct_cards_bin=1,
        bin_samples=0,
        bin_denies=0,
        amount_cents=15000,
        ip_country="BR",
        bin_country="BR",
        disposable_email=False,
        history_cents=[],
        naive_velocity=False,
    )
    base.update(overrides)
    return Snapshot(**base)


def test_limiares(rules):
    thresholds = rules["thresholds"]
    assert decide(29, thresholds) == "approve"
    assert decide(30, thresholds) == "challenge"
    assert decide(69, thresholds) == "challenge"
    assert decide(70, thresholds) == "deny"


def test_pagamento_limpo_aprova(rules):
    decision, total, reasons = score(_snapshot(), rules)
    assert decision == "approve"
    assert total == 0
    assert reasons == []


def test_velocity_sem_controle_ignora_o_mesmo_cartao(rules):
    decision, _, reasons = score(_snapshot(card_attempts=50, bin_attempts=50, naive_velocity=True), rules)
    assert decision == "approve"
    assert reasons == []


def test_velocity_com_controle_nega_o_mesmo_cartao(rules):
    limit = int(rules["velocity"]["max_attempts_per_card"])
    decision, _, reasons = score(_snapshot(card_attempts=limit), rules)
    assert decision == "deny"
    assert reasons[0].rule == "velocity"


def test_card_testing_por_bin(rules):
    limit = int(rules["card_testing"]["max_distinct_cards_per_bin"])
    decision, _, reasons = score(_snapshot(distinct_cards_bin=limit, amount_cents=500), rules)
    assert decision == "deny"
    assert any(item.rule == "card_testing" for item in reasons)


def test_geo_desafia(rules):
    decision, total, reasons = score(_snapshot(ip_country="BR", bin_country="US"), rules)
    assert decision == "challenge"
    assert total == int(rules["geo_bin"]["weight"])
    assert reasons[0].rule == "geo_bin"


def test_zscore_cold_start_nao_pontua(rules):
    decision, _, reasons = score(_snapshot(history_cents=[10000, 11000], amount_cents=9_000_000), rules)
    assert decision == "approve"
    assert reasons == []


def test_zscore_outlier_desafia(rules):
    history = [10000, 11000, 9000, 10500, 9500]
    decision, _, reasons = score(_snapshot(history_cents=history, amount_cents=1_000_000), rules)
    assert decision == "challenge"
    assert any(item.rule == "zscore" for item in reasons)


def test_sinais_forjados_dependem_do_que_o_servidor_ve():
    tables = load_tables(
        "config/bins.csv",
        "config/ip_countries.csv",
        "config/disposable_domains.txt",
        "BR",
    )
    payload = PaymentIn(
        amount="150.00",
        currency="BRL",
        card="4000000000000001",
        bin="400000",
        customer_id="cust_1",
        ip="198.51.100.8",
        email="a@mailinator.com",
        country="US",
    )
    aberto = resolve_signals(payload, "127.0.0.1", tables, naive_signals=True, naive_velocity=False)
    fechado = resolve_signals(payload, "127.0.0.1", tables, naive_signals=False, naive_velocity=False)
    assert aberto.ip_country == "US"
    assert aberto.disposable_email is False
    assert fechado.ip_country == "BR"
    assert fechado.bin_country == "US"
    assert fechado.scoring_bin == "400000"
    assert fechado.disposable_email is True
