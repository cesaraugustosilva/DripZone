from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details=None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_payload(code: str, message: str, details=None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code, content=error_payload(exc.code, exc.message, exc.details))
