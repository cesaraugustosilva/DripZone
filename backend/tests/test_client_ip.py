import pytest

from app.config import Settings
from app.utils.client_ip import MAX_X_FORWARDED_FOR_LENGTH, resolve_client_ip


def networks(*values: str):
    return Settings(trusted_proxies=",".join(values)).trusted_proxy_networks


def test_direct_peer_without_forwarded_headers_returns_peer_ip():
    assert resolve_client_ip("203.0.113.10", {}, networks()) == "203.0.113.10"


def test_direct_untrusted_peer_ignores_spoofed_x_forwarded_for():
    resolved = resolve_client_ip("203.0.113.10", {"x-forwarded-for": "8.8.8.8"}, networks())

    assert resolved == "203.0.113.10"


def test_trusted_proxy_uses_single_x_forwarded_for_client():
    resolved = resolve_client_ip("10.0.0.2", {"x-forwarded-for": "198.51.100.7"}, networks("10.0.0.2"))

    assert resolved == "198.51.100.7"


def test_trusted_proxy_walks_x_forwarded_for_chain_from_the_right():
    trusted = networks("10.0.0.0/24")
    resolved = resolve_client_ip(
        "10.0.0.3",
        {"x-forwarded-for": "198.51.100.7, 10.0.0.2"},
        trusted,
    )

    assert resolved == "198.51.100.7"


def test_trusted_proxy_handles_multiple_trusted_proxy_hops():
    trusted = networks("10.0.0.0/24", "192.0.2.0/24")
    resolved = resolve_client_ip(
        "10.0.0.3",
        {"x-forwarded-for": "198.51.100.7, 192.0.2.10, 10.0.0.2"},
        trusted,
    )

    assert resolved == "198.51.100.7"


def test_invalid_x_forwarded_for_falls_back_to_peer_ip():
    trusted = networks("10.0.0.0/24")

    assert resolve_client_ip("10.0.0.3", {"x-forwarded-for": "not-an-ip"}, trusted) == "10.0.0.3"
    assert resolve_client_ip("10.0.0.3", {"x-forwarded-for": "198.51.100.7:1234"}, trusted) == "10.0.0.3"


def test_empty_x_forwarded_for_falls_back_to_peer_ip():
    assert resolve_client_ip("10.0.0.3", {"x-forwarded-for": ""}, networks("10.0.0.0/24")) == "10.0.0.3"


def test_ipv6_client_in_x_forwarded_for():
    trusted = networks("2001:db8:1::/64")
    resolved = resolve_client_ip("2001:db8:1::10", {"x-forwarded-for": "2001:db8:2::20"}, trusted)

    assert resolved == "2001:db8:2::20"


def test_ipv6_trusted_proxy_with_x_real_ip_fallback():
    trusted = networks("::1")
    resolved = resolve_client_ip("::1", {"x-real-ip": "2001:db8::5"}, trusted)

    assert resolved == "2001:db8::5"


def test_cidr_matching_allows_trusted_proxy_range():
    trusted = networks("172.16.0.0/12")
    resolved = resolve_client_ip("172.19.0.2", {"x-forwarded-for": "198.51.100.9"}, trusted)

    assert resolved == "198.51.100.9"


def test_oversized_x_forwarded_for_falls_back_to_peer_ip():
    trusted = networks("10.0.0.0/24")
    oversized = "1" * (MAX_X_FORWARDED_FOR_LENGTH + 1)

    assert resolve_client_ip("10.0.0.3", {"x-forwarded-for": oversized}, trusted) == "10.0.0.3"


def test_malformed_trusted_proxy_config_fails_fast():
    with pytest.raises(ValueError, match="TRUSTED_PROXIES"):
        Settings(trusted_proxies="not-a-cidr")
