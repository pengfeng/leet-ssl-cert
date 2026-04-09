"""Cloudflare DNS provider."""

from __future__ import annotations

from typing import Any

from requests import Session

from ..errors import DNSError
from .base import DNSProvider


class CloudflareDNSProvider(DNSProvider):
    """Cloudflare implementation for ACME DNS-01 challenges."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        super().__init__(settings=settings)
        self.api_token = str(self.settings.get("api_token", "")).strip()
        if not self.api_token:
            raise DNSError("cloudflare provider requires api_token")
        self.base_url = str(self.settings.get("base_url", "https://api.cloudflare.com/client/v4")).rstrip("/")
        self._session = Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            }
        )

    def validate_credentials(self) -> None:
        self._list_zones(params={"per_page": 1})

    def create_txt_record(self, zone: str, record_name: str, value: str) -> None:
        zone_id = self._find_zone_id(zone)
        self._request(
            "POST",
            f"/zones/{zone_id}/dns_records",
            json={
                "type": "TXT",
                "name": record_name.rstrip("."),
                "content": value,
                "ttl": int(self.settings.get("ttl", 60)),
            },
        )

    def delete_txt_record(self, zone: str, record_name: str, value: str) -> None:
        zone_id = self._find_zone_id(zone)
        response = self._request(
            "GET",
            f"/zones/{zone_id}/dns_records",
            params={"type": "TXT", "name": record_name.rstrip(".")},
        )
        for record in response:
            if record.get("content") == value:
                self._request("DELETE", f"/zones/{zone_id}/dns_records/{record['id']}")

    def find_zone_for_domain(self, domain: str) -> str:
        parts = domain.rstrip(".").split(".")
        for index in range(len(parts) - 1):
            candidate = ".".join(parts[index:])
            zones = self._list_zones(params={"name": candidate, "per_page": 1})
            if zones:
                return candidate
        raise DNSError(f"Unable to find a Cloudflare zone for {domain}")

    def _find_zone_id(self, zone: str) -> str:
        zones = self._list_zones(params={"name": zone.rstrip("."), "per_page": 1})
        if not zones:
            raise DNSError(f"Unable to find Cloudflare zone {zone}")
        return zones[0]["id"]

    def _list_zones(self, *, params: dict[str, Any]) -> list[dict[str, Any]]:
        result = self._request("GET", "/zones", params=params)
        if not isinstance(result, list):
            raise DNSError("Unexpected response while listing Cloudflare zones")
        return result

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        response = self._session.request(method, f"{self.base_url}{path}", params=params, json=json, timeout=30)
        try:
            payload = response.json()
        except ValueError as exc:
            raise DNSError(f"Cloudflare API returned non-JSON response for {path}") from exc
        if not response.ok or not payload.get("success", False):
            errors = payload.get("errors") or [payload]
            raise DNSError(f"Cloudflare API request failed for {path}: {errors}")
        return payload.get("result")
