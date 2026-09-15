from __future__ import annotations

from collections.abc import Mapping, Sequence
import ipaddress

from fastapi import Request


MAX_X_FORWARDED_FOR_LENGTH = 1024
MAX_X_FORWARDED_FOR_HOPS = 20

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_ip(value: str | None) -> IPAddress | None:
    if not value:
        return None
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def is_trusted_proxy(address: IPAddress, trusted_proxies: Sequence[IPNetwork]) -> bool:
    return any(address in network for network in trusted_proxies)


def parse_x_forwarded_for(value: str | None) -> list[IPAddress] | None:
    if not value or len(value) > MAX_X_FORWARDED_FOR_LENGTH:
        return None
    hops = [hop.strip() for hop in value.split(",")]
    if not hops or len(hops) > MAX_X_FORWARDED_FOR_HOPS or any(not hop for hop in hops):
        return None
    parsed = [parse_ip(hop) for hop in hops]
    if any(address is None for address in parsed):
        return None
    return [address for address in parsed if address is not None]


def resolve_client_ip(
    peer_host: str | None,
    headers: Mapping[str, str],
    trusted_proxies: Sequence[IPNetwork],
) -> str:
    fallback = peer_host or "local"
    peer_ip = parse_ip(peer_host)
    if peer_ip is None or not is_trusted_proxy(peer_ip, trusted_proxies):
        return fallback

    x_forwarded_for = parse_x_forwarded_for(headers.get("x-forwarded-for"))
    if x_forwarded_for:
        for address in reversed(x_forwarded_for):
            if not is_trusted_proxy(address, trusted_proxies):
                return str(address)
        return str(x_forwarded_for[0])

    real_ip = parse_ip(headers.get("x-real-ip"))
    if real_ip is not None:
        return str(real_ip)

    return fallback


def get_client_ip(request: Request) -> str:
    peer_host = request.client.host if request.client else None
    return resolve_client_ip(peer_host, request.headers, request.app.state.settings.trusted_proxy_networks)
