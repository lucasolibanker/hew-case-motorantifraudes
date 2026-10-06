"""Máscara de PAN.

O número completo existe só na memória do request, entre a validação e
o HMAC. Log, Redis e Postgres ficam com o digest e os últimos 4.
"""

from __future__ import annotations

import hashlib
import hmac
import re

# 13 a 19 dígitos, com espaço ou hífen no meio. Cobre o PAN colado em log.
_PAN_PATTERN = re.compile(r"\b(?:\d[ -]*?){12,18}\d\b")


def normalize_pan(card: str) -> str:
    """Tira espaço e hífen antes de qualquer comparação.

    Sem isto, o mesmo cartão com um espaço no meio vira outro fingerprint
    e o velocity por cartão não vê a repetição.
    """
    return re.sub(r"[ -]", "", card)


def last4(pan_digits: str) -> str:
    return pan_digits[-4:]


def fingerprint(pan_digits: str, pepper: str) -> str:
    """HMAC, não SHA-256 puro.

    Um hash sem pepper é reversível por tabela arco-íris de PAN (o espaço
    de cartões é pequeno). O pepper fica só no ambiente.
    """
    return hmac.new(pepper.encode(), pan_digits.encode(), hashlib.sha256).hexdigest()


def redact_pan(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) < 13 or len(digits) > 19:
            return match.group(0)
        return "****" + digits[-4:]

    return _PAN_PATTERN.sub(_replace, text)
