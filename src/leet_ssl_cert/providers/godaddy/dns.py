"""GoDaddy DNS provider."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, parse, request

from leet_ssl_cert.errors import DNSError
from leet_ssl_cert.providers.base import DNSProvider


class GoDaddyDNSProvider(DNSProvider):
    """GoDaddy Domains API implementation for ACME DNS-01 challenges."""

    def validate_credentials(self) -> None:
        try:
            self._list_domains(limit=1)
        except DNSError:
            raise
        except Exception as exc:
            raise DNSError(f"GoDaddy DNS credential validation failed: {exc}") from exc

    def create_txt_record(self, zone: str, record_name: str, value: str) -> None:
        try:
            name = self._relative_record_name(zone, record_name)
            existing = self._get_txt_records(zone, name)
            records_by_value = {
                item["data"]: item for item in existing if item.get("data")
            }
            records_by_value.setdefault(value, {"data": value})
            self._replace_txt_records(zone, name, list(records_by_value.values()))
        except DNSError:
            raise
        except Exception as exc:
            raise DNSError(
                f"Failed creating GoDaddy TXT record {record_name}: {exc}"
            ) from exc

    def delete_txt_record(self, zone: str, record_name: str, value: str) -> None:
        try:
            name = self._relative_record_name(zone, record_name)
            existing = self._get_txt_records(zone, name)
            if not existing:
                return
            remaining = [item for item in existing if item.get("data") != value]
            if remaining:
                self._replace_txt_records(zone, name, remaining)
                return
            self._request("DELETE", self._records_path(zone, name), not_found_ok=True)
        except DNSError:
            raise
        except Exception as exc:
            raise DNSError(
                f"Failed deleting GoDaddy TXT record {record_name}: {exc}"
            ) from exc

    def find_zone_for_domain(self, domain: str) -> str:
        try:
            candidates = [
                str(item.get("domain", "")).strip().rstrip(".")
                for item in self._list_domains()
                if item.get("domain")
            ]
        except DNSError:
            raise
        except Exception as exc:
            raise DNSError(f"Failed listing GoDaddy domains: {exc}") from exc
        matches = [
            candidate
            for candidate in candidates
            if domain == candidate or domain.endswith(f".{candidate}")
        ]
        if not matches:
            raise DNSError(f"Unable to find a GoDaddy DNS zone for {domain}")
        return max(matches, key=len)

    def _list_domains(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        domains: list[dict[str, Any]] = []
        marker: str | None = None
        while True:
            query: dict[str, Any] = {"limit": limit}
            if marker:
                query["marker"] = marker
            page = self._request("GET", "/v1/domains", query=query)
            if page is None:
                return domains
            if not isinstance(page, list):
                raise DNSError("Unexpected response while listing GoDaddy domains")
            domains.extend(item for item in page if isinstance(item, dict))
            if len(page) < limit:
                return domains
            next_marker = str(page[-1].get("domain", "")).strip()
            if not next_marker or next_marker == marker:
                return domains
            marker = next_marker

    def _get_txt_records(self, zone: str, name: str) -> list[dict[str, Any]]:
        records = self._request(
            "GET", self._records_path(zone, name), not_found_ok=True
        )
        if records is None:
            return []
        if not isinstance(records, list):
            raise DNSError(
                f"Unexpected response while reading GoDaddy TXT record {name}"
            )
        return [item for item in records if isinstance(item, dict)]

    def _replace_txt_records(
        self, zone: str, name: str, records: list[dict[str, Any]]
    ) -> None:
        default_ttl = self._configured_ttl()
        if default_ttl is None:
            default_ttl = next(
                (int(item["ttl"]) for item in records if item.get("ttl") is not None),
                None,
            )
        payload = [
            self._record_payload(item, default_ttl=default_ttl)
            for item in records
            if item.get("data")
        ]
        self._request("PUT", self._records_path(zone, name), payload=payload)

    def _record_payload(
        self, record: dict[str, Any], *, default_ttl: int | None
    ) -> dict[str, Any]:
        payload = {"data": str(record["data"])}
        ttl = record.get("ttl", default_ttl)
        if ttl is not None:
            payload["ttl"] = int(ttl)
        return payload

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        payload: Any | None = None,
        not_found_ok: bool = False,
    ) -> Any | None:
        url = self._build_url(path, query=query)
        data: bytes | None = None
        headers = {
            "Accept": "application/json",
            "Authorization": self._authorization_header(),
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        shopper_id = self._shopper_id()
        if shopper_id:
            headers["X-Shopper-Id"] = shopper_id
        req = request.Request(url, data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=self._timeout_seconds()) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            if exc.code == 404 and not_found_ok:
                return None
            raise DNSError(
                f"GoDaddy API request failed with HTTP {exc.code}: {self._read_error_body(exc)}"
            ) from exc
        except error.URLError as exc:
            raise DNSError(f"GoDaddy API request failed: {exc.reason}") from exc
        if not raw:
            return None
        return json.loads(raw)

    def _read_error_body(self, exc: error.HTTPError) -> str:
        try:
            raw = exc.read().decode("utf-8")
        except Exception:
            return exc.reason or "unknown error"
        if not raw:
            return exc.reason or "unknown error"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        if isinstance(data, dict):
            if data.get("message"):
                return str(data["message"])
            if data.get("detail"):
                return str(data["detail"])
        return raw

    def _build_url(self, path: str, *, query: dict[str, Any] | None = None) -> str:
        base_url = self._base_url().rstrip("/")
        if not query:
            return f"{base_url}{path}"
        return f"{base_url}{path}?{parse.urlencode(query)}"

    def _records_path(self, zone: str, name: str) -> str:
        return f"/v1/domains/{parse.quote(zone, safe='')}/records/TXT/{parse.quote(name, safe='')}"

    def _authorization_header(self) -> str:
        api_key = self.settings.get("api_key") or os.getenv("GODADDY_API_KEY")
        api_secret = self.settings.get("api_secret") or os.getenv("GODADDY_API_SECRET")
        if not api_key or not api_secret:
            raise DNSError("godaddy provider requires api_key and api_secret")
        return f"sso-key {api_key}:{api_secret}"

    def _shopper_id(self) -> str | None:
        shopper_id = str(
            self.settings.get("shopper_id") or os.getenv("GODADDY_SHOPPER_ID") or ""
        ).strip()
        return shopper_id or None

    def _base_url(self) -> str:
        return str(
            self.settings.get("api_base_url")
            or os.getenv("GODADDY_API_BASE_URL")
            or "https://api.godaddy.com"
        )

    def _timeout_seconds(self) -> int:
        return int(self.settings.get("timeout", 30))

    def _configured_ttl(self) -> int | None:
        ttl = self.settings.get("ttl")
        if ttl in (None, ""):
            return None
        return int(ttl)

    def _relative_record_name(self, zone: str, record_name: str) -> str:
        normalized = record_name.rstrip(".")
        normalized_zone = zone.rstrip(".")
        if normalized == normalized_zone:
            return "@"
        suffix = f".{normalized_zone}"
        if normalized.endswith(suffix):
            candidate = normalized[: -len(suffix)]
            return candidate or "@"
        return normalized
