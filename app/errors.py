"""Erros de domínio com status HTTP explícito.

FastAPI transformaria um ValueError genérico em 500. Aqui o chamador
escolhe o status: 400 da chave ausente, 401 do webhook, 409 do replay.
"""


class AppError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
