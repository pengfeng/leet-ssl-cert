"""Google Cloud DNS provider."""

from __future__ import annotations

from typing import Any

from leet_ssl_cert.errors import DNSError
from leet_ssl_cert.providers.base import DNSProvider
from leet_ssl_cert.providers.gcp.common import resolve_gcp_project


class GCPCloudDNSProvider(DNSProvider):
    """Google Cloud DNS implementation for ACME DNS-01 challenges."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        super().__init__(settings=settings)
        self._client: Any | None = None

    def validate_credentials(self) -> None:
        try:
            next(iter(self._client_or_raise().list_zones(max_results=1)), None)
        except DNSError:
            raise
        except Exception as exc:
            raise DNSError(f"Google Cloud DNS credential validation failed: {exc}") from exc

    def create_txt_record(self, zone: str, record_name: str, value: str) -> None:
        try:
            managed_zone = self._find_managed_zone(zone)
            existing = self._find_txt_record_set(managed_zone, record_name)
            values = sorted({*self._record_values(existing), value})
            self._apply_txt_record_set(managed_zone, record_name, values, existing)
        except DNSError:
            raise
        except Exception as exc:
            raise DNSError(f"Failed creating Google Cloud DNS TXT record {record_name}: {exc}") from exc

    def delete_txt_record(self, zone: str, record_name: str, value: str) -> None:
        try:
            managed_zone = self._find_managed_zone(zone)
            existing = self._find_txt_record_set(managed_zone, record_name)
            if existing is None:
                return
            values = [item for item in self._record_values(existing) if item != value]
            self._apply_txt_record_set(managed_zone, record_name, values, existing)
        except DNSError:
            raise
        except Exception as exc:
            raise DNSError(f"Failed deleting Google Cloud DNS TXT record {record_name}: {exc}") from exc

    def find_zone_for_domain(self, domain: str) -> str:
        try:
            matches = [
                zone.dns_name.rstrip(".")
                for zone in self._client_or_raise().list_zones()
                if domain == zone.dns_name.rstrip(".") or domain.endswith(f".{zone.dns_name.rstrip('.')}")
            ]
        except DNSError:
            raise
        except Exception as exc:
            raise DNSError(f"Failed listing Google Cloud DNS zones: {exc}") from exc
        if not matches:
            raise DNSError(f"Unable to find a Google Cloud DNS zone for {domain}")
        return max(matches, key=len)

    def _build_client(self) -> Any:
        project = self._project()
        try:
            from google.cloud import dns
        except ImportError as exc:
            raise DNSError("google-cloud-dns is not installed. Install leet-ssl-cert[gcp].") from exc
        return dns.Client(project=project)

    def _client_or_raise(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _project(self) -> str:
        project = resolve_gcp_project(self.settings)
        if not project:
            raise DNSError("gcp provider requires project, GCP_PROJECT, or GOOGLE_CLOUD_PROJECT")
        return project

    def _find_managed_zone(self, zone_name: str) -> Any:
        normalized = zone_name.rstrip(".")
        for managed_zone in self._client_or_raise().list_zones():
            if managed_zone.dns_name.rstrip(".") == normalized:
                return managed_zone
        raise DNSError(f"Unable to find Google Cloud DNS zone {zone_name}")

    def _find_txt_record_set(self, managed_zone: Any, record_name: str) -> Any | None:
        fqdn = self._fqdn(record_name)
        for record_set in managed_zone.list_resource_record_sets():
            if record_set.record_type == "TXT" and record_set.name.rstrip(".") == fqdn.rstrip("."):
                return record_set
        return None

    def _apply_txt_record_set(
        self,
        managed_zone: Any,
        record_name: str,
        values: list[str],
        existing: Any | None,
    ) -> None:
        changes = managed_zone.changes()
        if existing is not None:
            changes.delete_record_set(existing)
        if values:
            changes.add_record_set(
                managed_zone.resource_record_set(
                    self._fqdn(record_name),
                    "TXT",
                    int(self.settings.get("ttl", 60)),
                    [self._txt_rrdata(item) for item in values],
                )
            )
        changes.create(client=self._client_or_raise())

    def _record_values(self, record_set: Any | None) -> list[str]:
        if record_set is None:
            return []
        return [self._normalize_rrdata(item) for item in getattr(record_set, "rrdatas", []) or []]

    def _normalize_rrdata(self, value: str) -> str:
        normalized = str(value).strip()
        if len(normalized) >= 2 and normalized[0] == normalized[-1] == '"':
            return normalized[1:-1]
        return normalized

    def _txt_rrdata(self, value: str) -> str:
        return f'"{value}"' if any(ch.isspace() for ch in value) else value

    def _fqdn(self, record_name: str) -> str:
        return f"{record_name.rstrip('.')}."
