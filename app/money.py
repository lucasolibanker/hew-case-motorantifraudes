"""Conversão de dinheiro sem float.

Float de 10.10 não é exatamente 1010 centavos. O request entra como Decimal
e o resto do sistema fala centavos inteiros.
"""

from decimal import Decimal, ROUND_HALF_UP

from app.errors import AppError


def to_cents(amount: Decimal) -> int:
    quantized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if quantized != amount:
        raise AppError(422, "amount aceita no máximo 2 casas decimais")
    return int((quantized * 100).to_integral_value(rounding=ROUND_HALF_UP))


def from_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    value = abs(cents)
    return f"{sign}{value // 100}.{value % 100:02d}"
