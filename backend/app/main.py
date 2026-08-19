from pathlib import Path
from time import perf_counter
from uuid import uuid4
import logging

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.exc import IntegrityError

from app.api.router import api_router
from app.config import settings
from app.dependencies import require_csrf
from app.exceptions import ApiError, api_error_handler, error_payload

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("dripzone.requests")

app = FastAPI(title=settings.app_name, version=settings.version, debug=settings.app_debug)
app.state.settings = settings


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        start = perf_counter()
        response = await call_next(request)
        elapsed_ms = round((perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_complete",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": elapsed_ms,
            },
        )
        return response


app.add_middleware(RequestIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

app.add_exception_handler(ApiError, api_error_handler)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request, exc):
    return error_payload_response(409, "CONFLICT", "Registro duplicado ou em uso.")


def error_payload_response(status_code: int, code: str, message: str):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status_code, content=error_payload(code, message))


app.include_router(api_router, prefix=settings.api_prefix)

upload_root = Path(settings.upload_directory)
upload_root.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_root), name="uploads")


@app.get("/")
def root():
    return {"service": settings.app_name, "api": settings.api_prefix}
