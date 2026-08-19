from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.exceptions import ApiError

ALLOWED_EXTERNAL_PORTS = {80, 443}


def normalize_hostname(hostname: str) -> str:
    return hostname.strip().lower().rstrip(".").encode("idna").decode("ascii")


def validate_url_authority(url: str, *, code: str, message: str) -> None:
    parsed = urlparse(str(url).strip())
    if parsed.username or parsed.password:
        raise ApiError(422, code, message, {"blocker": "userinfo_not_allowed"})
    try:
        port = parsed.port
    except ValueError as exc:
        raise ApiError(422, code, message, {"blocker": "invalid_port"}) from exc
    if port is not None and port not in ALLOWED_EXTERNAL_PORTS:
        raise ApiError(422, code, message, {"blocker": "port_not_allowed"})


def normalized_netloc(hostname: str, port: int | None = None) -> str:
    host = normalize_hostname(hostname)
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{port}" if port else host


def parse_ipv4_numeric_literal(hostname: str) -> str | None:
    parts = hostname.strip().lower().rstrip(".").split(".")
    if not parts or any(part == "" for part in parts):
        return None
    values: list[int] = []
    try:
        for part in parts:
            base = 10
            value_text = part
            if value_text.startswith("0x"):
                base = 16
            elif len(value_text) > 1 and value_text.startswith("0"):
                base = 8
            values.append(int(value_text, base))
    except ValueError:
        return None
    if len(values) == 1:
        value = values[0]
        if 0 <= value <= 0xFFFFFFFF:
            return str(ipaddress.IPv4Address(value))
        return None
    if len(values) > 4 or any(value < 0 or value > 255 for value in values):
        return None
    return str(ipaddress.IPv4Address(".".join(str(value) for value in values)))


def resolve_public_hostname(hostname: str) -> list[str]:
    normalized = normalize_hostname(hostname)
    numeric = parse_ipv4_numeric_literal(normalized)
    if numeric:
        return [numeric]
    try:
        return [str(ipaddress.ip_address(normalized))]
    except ValueError:
        pass
    try:
        info = socket.getaddrinfo(normalized, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ApiError(422, "URL_HOST_NOT_RESOLVED", "Nao foi possivel validar o host informado.", {"blocker": "blocked_host"}) from exc
    addresses = sorted({item[4][0] for item in info})
    if not addresses:
        raise ApiError(422, "URL_HOST_NOT_RESOLVED", "Nao foi possivel validar o host informado.", {"blocker": "blocked_host"})
    return addresses


def is_blocked_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return (
        not ip.is_global
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )
