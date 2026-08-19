from __future__ import annotations

import os
import ssl
from pathlib import Path

import certifi

from app.exceptions import ApiError


TLS_ERROR_MESSAGE = (
    "Nao foi possivel validar o certificado HTTPS da origem. "
    "Verifique os certificados confiaveis do Windows, o ambiente virtual ou configure DRIPZONE_CA_BUNDLE."
)


def build_verified_ssl_context() -> ssl.SSLContext:
    bundle = os.environ.get("DRIPZONE_CA_BUNDLE", "").strip()
    if bundle:
        bundle_path = Path(bundle)
        if not bundle_path.is_file():
            raise ApiError(422, "IMPORT_TLS_CA_BUNDLE_INVALID", TLS_ERROR_MESSAGE)
        context = ssl.create_default_context(cafile=str(bundle_path))
    else:
        context = build_system_ssl_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def build_system_ssl_context() -> ssl.SSLContext:
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context(cafile=certifi.where())


def is_tls_verification_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    while current:
        if isinstance(current, ssl.SSLError):
            return True
        current = current.__cause__ or current.__context__
    message = str(exc).casefold()
    return "certificate_verify_failed" in message or "certificate verify failed" in message
