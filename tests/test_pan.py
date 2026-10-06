from decimal import Decimal

import pytest

from app.errors import AppError
from app.money import from_cents, to_cents
from app.security.pan import fingerprint, last4, normalize_pan, redact_pan


def test_normaliza_espaco_antes_do_fingerprint():
    assert normalize_pan("4111 1111-1111 1111") == "4111111111111111"


def test_fingerprint_muda_com_o_pepper_e_nao_e_o_pan():
    pan = "4111111111111111"
    first = fingerprint(pan, "pepper-a")
    second = fingerprint(pan, "pepper-b")
    assert first != second
    assert pan not in first
    assert last4(pan) == "1111"


def test_redige_pan_no_texto():
    text = redact_pan("tentou 4111 1111 1111 1111 agora")
    assert "4111 1111 1111 1111" not in text
    assert "1111" in text


def test_centavos_rejeitam_terceira_casa():
    with pytest.raises(AppError):
        to_cents(Decimal("10.001"))
    assert to_cents(Decimal("10.10")) == 1010
    assert from_cents(1010) == "10.10"
