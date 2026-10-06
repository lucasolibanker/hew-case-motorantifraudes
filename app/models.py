"""Corpo do POST /payments e da verificação.

extra=forbid: campo que não conhecemos não entra calado. Um `country`
existe de propósito. Com o controle ligado, ele não entra no score.
"""

from __future__ import annotations

import ipaddress
import re
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CUSTOMER = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


class PaymentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, le=Decimal("1000000"))
    currency: str
    card: str
    bin: str
    customer_id: str
    ip: str
    email: str
    # Opcional. Cliente pode mandar. Não é observação nossa.
    country: str | None = None

    @field_validator("currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        code = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", code):
            raise ValueError("currency deve ter 3 letras")
        return code

    @field_validator("card")
    @classmethod
    def card_digits(cls, value: str) -> str:
        digits = re.sub(r"[ -]", "", value)
        if not digits.isdigit() or not 13 <= len(digits) <= 19:
            raise ValueError("card deve ter de 13 a 19 dígitos")
        return digits

    @field_validator("bin")
    @classmethod
    def bin_digits(cls, value: str) -> str:
        digits = value.strip()
        if not re.fullmatch(r"\d{6}", digits):
            raise ValueError("bin deve ter 6 dígitos")
        return digits

    @field_validator("customer_id")
    @classmethod
    def customer(cls, value: str) -> str:
        cleaned = value.strip()
        if not _CUSTOMER.fullmatch(cleaned):
            raise ValueError("customer_id inválido")
        return cleaned

    @field_validator("ip")
    @classmethod
    def ip_addr(cls, value: str) -> str:
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError as exc:
            raise ValueError("ip inválido") from exc

    @field_validator("email")
    @classmethod
    def email_addr(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not _EMAIL.fullmatch(cleaned) or len(cleaned) > 254:
            raise ValueError("email inválido")
        return cleaned

    @field_validator("country")
    @classmethod
    def country_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        code = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", code):
            raise ValueError("country deve ter 2 letras")
        return code


class VerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str


class ReasonOut(BaseModel):
    rule: str
    weight: int
    detail: str


class PaymentOut(BaseModel):
    id: str
    amount: str
    currency: str
    decision: str
    risk_score: int
    reasons: list[ReasonOut]
    status: str
    psp: str
    otp_demo: str | None = None


class DecisionRecord(BaseModel):
    decision: str
    risk_score: int
    reasons: list[ReasonOut]
    created_at: str


class PaymentState(BaseModel):
    id: str
    status: str
    amount: str
    currency: str
    pan_last4: str
    customer_id: str
    email: str
    observed_ip: str
    client_ip: str
    bin: str
    client_bin: str
    client_country: str | None
    decisions: list[DecisionRecord]
