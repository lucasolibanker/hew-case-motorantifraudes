"""Filtro de log.

A garantia principal é não logar o cartão. Esta formatação é a segunda
linha, caso alguém passe o PAN numa mensagem no futuro.
"""

from __future__ import annotations

import logging

from app.security.pan import redact_pan

log = logging.getLogger("antifraud")


class _RedactFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_pan(super().format(record))


def install_logging() -> None:
    log.handlers.clear()
    log.propagate = False
    log.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(_RedactFormatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
