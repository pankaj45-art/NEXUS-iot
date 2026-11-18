from __future__ import annotations


class ApiError(Exception):
    def __init__(self, status: int, message: str, code: str = "error",
                 extra: dict | None = None, extra_headers: dict | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code
        self.extra = extra or {}
        self.extra_headers: dict = extra_headers or {}

    def payload(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, **self.extra}}
