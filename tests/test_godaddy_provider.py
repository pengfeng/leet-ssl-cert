from __future__ import annotations

import pytest

from leet_ssl_cert.errors import DNSError
from leet_ssl_cert.providers.godaddy.dns import GoDaddyDNSProvider


def test_godaddy_find_zone_uses_longest_matching_domain() -> None:
    provider = GoDaddyDNSProvider({"api_key": "key", "api_secret": "secret"})
    provider._request = lambda method, path, **kwargs: [  # type: ignore[method-assign]
        {"domain": "example.com"},
        {"domain": "sub.example.com"},
    ]

    assert provider.find_zone_for_domain("www.sub.example.com") == "sub.example.com"


def test_godaddy_create_merges_existing_txt_values() -> None:
    provider = GoDaddyDNSProvider({"api_key": "key", "api_secret": "secret"})
    calls: list[tuple[str, str, object | None]] = []

    def fake_request(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs.get("payload")))
        if method == "GET":
            return [{"data": "existing-token", "ttl": 600}]
        return None

    provider._request = fake_request  # type: ignore[method-assign]

    provider.create_txt_record(
        "example.com", "_acme-challenge.example.com", "new-token"
    )

    assert calls == [
        ("GET", "/v1/domains/example.com/records/TXT/_acme-challenge", None),
        (
            "PUT",
            "/v1/domains/example.com/records/TXT/_acme-challenge",
            [{"data": "existing-token", "ttl": 600}, {"data": "new-token", "ttl": 600}],
        ),
    ]


def test_godaddy_delete_removes_matching_value_only() -> None:
    provider = GoDaddyDNSProvider({"api_key": "key", "api_secret": "secret"})
    calls: list[tuple[str, str, object | None]] = []

    def fake_request(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs.get("payload")))
        if method == "GET":
            return [{"data": "keep-me", "ttl": 600}, {"data": "remove-me", "ttl": 600}]
        return None

    provider._request = fake_request  # type: ignore[method-assign]

    provider.delete_txt_record(
        "example.com", "_acme-challenge.example.com", "remove-me"
    )

    assert calls == [
        ("GET", "/v1/domains/example.com/records/TXT/_acme-challenge", None),
        (
            "PUT",
            "/v1/domains/example.com/records/TXT/_acme-challenge",
            [{"data": "keep-me", "ttl": 600}],
        ),
    ]


def test_godaddy_delete_removes_record_when_last_value_is_deleted() -> None:
    provider = GoDaddyDNSProvider({"api_key": "key", "api_secret": "secret"})
    calls: list[tuple[str, str, object | None]] = []

    def fake_request(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs.get("payload")))
        if method == "GET":
            return [{"data": "remove-me", "ttl": 600}]
        return None

    provider._request = fake_request  # type: ignore[method-assign]

    provider.delete_txt_record(
        "example.com", "_acme-challenge.example.com", "remove-me"
    )

    assert calls == [
        ("GET", "/v1/domains/example.com/records/TXT/_acme-challenge", None),
        ("DELETE", "/v1/domains/example.com/records/TXT/_acme-challenge", None),
    ]


def test_godaddy_relative_record_name_uses_apex_marker() -> None:
    provider = GoDaddyDNSProvider({"api_key": "key", "api_secret": "secret"})

    assert provider._relative_record_name("example.com", "example.com") == "@"


def test_godaddy_authorization_header_requires_credentials(monkeypatch) -> None:
    monkeypatch.delenv("GODADDY_API_KEY", raising=False)
    monkeypatch.delenv("GODADDY_API_SECRET", raising=False)
    provider = GoDaddyDNSProvider({})

    with pytest.raises(DNSError, match="requires api_key and api_secret"):
        provider._authorization_header()
