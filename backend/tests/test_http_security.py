import ssl
from pathlib import Path

import httpx
import pytest
import certifi

from app.exceptions import ApiError
from app.services import imports
from app.services.http_security import build_verified_ssl_context


class ResponseStream:
    def __init__(self, response: httpx.Response | None = None, error: Exception | None = None):
        self.response = response
        self.error = error

    def __enter__(self):
        if self.error:
            raise self.error
        return self.response

    def __exit__(self, exc_type, exc, tb):
        return False


def test_ssl_context_keeps_certificate_and_hostname_verification():
    context = build_verified_ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_explicit_ca_bundle_is_accepted(monkeypatch, tmp_path):
    bundle = tmp_path / "ca.pem"
    bundle.write_text(Path(certifi.where()).read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("DRIPZONE_CA_BUNDLE", str(bundle))
    context = build_verified_ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_missing_explicit_ca_bundle_raises_clear_error(monkeypatch):
    monkeypatch.setenv("DRIPZONE_CA_BUNDLE", "missing-ca.pem")
    with pytest.raises(ApiError) as exc:
        build_verified_ssl_context()
    assert exc.value.code == "IMPORT_TLS_CA_BUNDLE_INVALID"
    assert "DRIPZONE_CA_BUNDLE" in exc.value.message


def test_safe_fetcher_passes_ssl_context_to_httpx(monkeypatch):
    marker = object()
    captured = {}

    class PatchedClient:
        def __init__(self, *args, **kwargs):
            captured["verify"] = kwargs.get("verify")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url):
            return ResponseStream(httpx.Response(200, text="<html></html>", headers={"content-type": "text/html"}, request=httpx.Request(method, url)))

    monkeypatch.setattr(imports, "build_verified_ssl_context", lambda: marker)
    monkeypatch.setattr(imports, "resolve_source_hostname", lambda hostname: ["93.184.216.34"])
    monkeypatch.setattr(imports.httpx, "Client", PatchedClient)
    imports.SafeHTTPFetcher(["example.com"]).get("https://example.com/folder")
    assert captured["verify"] is marker
    assert captured["verify"] is not False


def test_tls_error_is_friendly_and_network_error_stays_timeout(monkeypatch):
    class TlsClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url):
            return ResponseStream(error=httpx.ConnectError("CERTIFICATE_VERIFY_FAILED"))

    monkeypatch.setattr(imports, "resolve_source_hostname", lambda hostname: ["93.184.216.34"])
    monkeypatch.setattr(imports.httpx, "Client", lambda *args, **kwargs: TlsClient())
    with pytest.raises(ApiError) as tls_error:
        imports.SafeHTTPFetcher(["example.com"]).get("https://example.com/folder")
    assert tls_error.value.code == "IMPORT_TLS_VERIFICATION_FAILED"
    assert "DRIPZONE_CA_BUNDLE" in tls_error.value.message

    class NetworkClient(TlsClient):
        def stream(self, method, url):
            return ResponseStream(error=httpx.ConnectError("network down"))

    monkeypatch.setattr(imports.httpx, "Client", lambda *args, **kwargs: NetworkClient())
    with pytest.raises(ApiError) as network_error:
        imports.SafeHTTPFetcher(["example.com"]).get("https://example.com/folder")
    assert network_error.value.code == "IMPORT_SOURCE_TIMEOUT"
