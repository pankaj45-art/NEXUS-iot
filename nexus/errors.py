from __future__ import annotations


class ApiError(Exception):
    def __init__(self, status: int, message: str, code: str = "error", extra: dict | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code
        self.extra = extra or {}

    def payload(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, **self.extra}}
