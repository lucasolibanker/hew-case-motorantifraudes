"""Assinatura do webhook do PSP.

O arquivo não se chama hmac.py: um módulo com esse nome, dentro do pacote,
faz `import hmac` carregar a si mesmo e esconder a biblioteca padrão.
"""

from __future__ import annotations

import hashlib
import hmac
import time


def sign(secret: str, timestamp: str, raw_body: bytes) -> str:
    """MAC de timestamp + '.' + corpo cru.

    Incluir o timestamp no MAC impede reusar uma assinatura válida com
    outra hora. O id do evento, mais abaixo, cobre o replay dentro da
    janela em que o timestamp ainda seria aceito.
    """
    message = timestamp.encode() + b"." + raw_body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _compare(expected: str, provided: str) -> bool:
    # compare_digest exige o mesmo tamanho e levanta erro se diferir.
    # Tamanho errado já é assinatura inválida, sem exceção.
    if len(provided) != len(expected):
        return False
    return hmac.compare_digest(expected, provided)


def timestamp_fresh(timestamp: str, now: int, tolerance_seconds: int) -> bool:
    try:
        sent = int(timestamp)
    except (TypeError, ValueError):
        return False
    return abs(now - sent) <= tolerance_seconds


def webhook_is_authentic(
    *,
    secret: str,
    timestamp: str,
    raw_body: bytes,
    signature: str,
    now: int | None = None,
    tolerance_seconds: int,
) -> bool:
    """Uma única falha, sem dizer se foi o MAC ou o relógio.

    Respostas diferentes ensinariam o atacante qual das duas checagens
    passou. As duas rodam sempre, inclusive quando o timestamp é lixo.
    """
    expected = sign(secret, timestamp or "", raw_body)
    signature_ok = _compare(expected, signature or "")
    fresh = timestamp_fresh(timestamp or "", now if now is not None else int(time.time()), tolerance_seconds)
    return signature_ok and fresh
