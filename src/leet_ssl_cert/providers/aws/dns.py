"""AWS Route 53 DNS provider."""

from __future__ import annotations

from typing import Any

from leet_ssl_cert.errors import DNSError
from leet_ssl_cert.providers.base import DNSProvider


class AWSRoute53DNSProvider(DNSProvider):
    """Route 53 implementation for ACME DNS-01 challenges."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        super().__init__(settings=settings)
        self._client: Any | None = None

    def validate_credentials(self) -> None:
        self._client_or_raise().list_hosted_zones(MaxItems="1")

    def create_txt_record(self, zone: str, record_name: str, value: str) -> None:
        hosted_zone = self._find_hosted_zone(zone)
        self._client_or_raise().change_resource_record_sets(
            HostedZoneId=hosted_zone["Id"].split("/")[-1],
            ChangeBatch={
                "Changes": [
                    {
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Name": self._fqdn(record_name),
                            "Type": "TXT",
                            "TTL": int(self.settings.get("ttl", 60)),
                            "ResourceRecords": [{"Value": f'"{value}"'}],
                        },
                    }
                ]
            },
        )

    def delete_txt_record(self, zone: str, record_name: str, value: str) -> None:
        hosted_zone = self._find_hosted_zone(zone)
        try:
            self._client_or_raise().change_resource_record_sets(
                HostedZoneId=hosted_zone["Id"].split("/")[-1],
                ChangeBatch={
                    "Changes": [
                        {
                            "Action": "DELETE",
                            "ResourceRecordSet": {
                                "Name": self._fqdn(record_name),
                                "Type": "TXT",
                                "TTL": int(self.settings.get("ttl", 60)),
                                "ResourceRecords": [{"Value": f'"{value}"'}],
                            },
                        }
                    ]
                },
            )
        except Exception as exc:
            if "not found" not in str(exc).lower():
                raise DNSError(f"Failed deleting Route 53 TXT record {record_name}: {exc}") from exc

    def find_zone_for_domain(self, domain: str) -> str:
        response = self._client_or_raise().list_hosted_zones()
        zones = response.get("HostedZones", [])
        candidates = [zone["Name"].rstrip(".") for zone in zones]
        matches = [candidate for candidate in candidates if domain == candidate or domain.endswith(f".{candidate}")]
        if not matches:
            raise DNSError(f"Unable to find a Route 53 hosted zone for {domain}")
        return max(matches, key=len)

    def _client_or_raise(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self) -> Any:
        try:
            import boto3
        except ImportError as exc:
            raise DNSError("boto3 is not installed. Install leet-ssl-cert[aws].") from exc
        session = boto3.session.Session(
            aws_access_key_id=self.settings.get("access_key_id"),
            aws_secret_access_key=self.settings.get("secret_access_key"),
            aws_session_token=self.settings.get("session_token"),
            region_name=self.settings.get("region"),
            profile_name=self.settings.get("profile"),
        )
        return session.client("route53")

    def _find_hosted_zone(self, zone_name: str) -> dict[str, Any]:
        response = self._client_or_raise().list_hosted_zones()
        for hosted_zone in response.get("HostedZones", []):
            if hosted_zone["Name"].rstrip(".") == zone_name.rstrip("."):
                return hosted_zone
        raise DNSError(f"Unable to find Route 53 hosted zone {zone_name}")

    def _fqdn(self, record_name: str) -> str:
        normalized = record_name.rstrip(".")
        return f"{normalized}."
