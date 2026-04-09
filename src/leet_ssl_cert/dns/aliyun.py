"""Alibaba Cloud DNS provider."""

from __future__ import annotations

from typing import Any

from ..errors import DNSError
from .base import DNSProvider


class AliyunDNSProvider(DNSProvider):
    """Alibaba Cloud DNS implementation for ACME DNS-01 challenges."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        super().__init__(settings=settings)
        self._client: Any | None = None

    def validate_credentials(self) -> None:
        request_cls = self._import_request("DescribeDomainsRequest")
        self._client_or_raise().describe_domains(request_cls(page_number=1, page_size=1))

    def create_txt_record(self, zone: str, record_name: str, value: str) -> None:
        request_cls = self._import_request("AddDomainRecordRequest")
        request = request_cls(
            domain_name=zone,
            rr=self._relative_record_name(zone, record_name),
            type="TXT",
            value=value,
        )
        self._client_or_raise().add_domain_record(request)

    def delete_txt_record(self, zone: str, record_name: str, value: str) -> None:
        request_cls = self._import_request("DescribeDomainRecordsRequest")
        request = request_cls(
            domain_name=zone,
            rrkey_word=self._relative_record_name(zone, record_name),
            type_key_word="TXT",
            value_key_word=value,
        )
        response = self._client_or_raise().describe_domain_records(request)
        record_id = None
        records = getattr(getattr(response.body, "domain_records", None), "record", []) or []
        for record in records:
            if getattr(record, "value", None) == value:
                record_id = getattr(record, "record_id", None)
                break
        if not record_id:
            return
        delete_request_cls = self._import_request("DeleteDomainRecordRequest")
        self._client_or_raise().delete_domain_record(delete_request_cls(record_id=record_id))

    def find_zone_for_domain(self, domain: str) -> str:
        request_cls = self._import_request("DescribeDomainsRequest")
        request = request_cls(page_number=1, page_size=100)
        response = self._client_or_raise().describe_domains(request)
        domains = getattr(getattr(response.body, "domains", None), "domain", []) or []
        candidates = [getattr(item, "domain_name", "") for item in domains]
        matches = [candidate for candidate in candidates if domain == candidate or domain.endswith(f".{candidate}")]
        if not matches:
            raise DNSError(f"Unable to find an Alibaba Cloud DNS zone for {domain}")
        return max(matches, key=len)

    def _build_client(self) -> Any:
        access_key_id = self.settings.get("access_key_id")
        access_key_secret = self.settings.get("access_key_secret")
        if not access_key_id or not access_key_secret:
            raise DNSError("aliyun provider requires access_key_id and access_key_secret")
        try:
            from alibabacloud_alidns20150109.client import Client as AlidnsClient
            from alibabacloud_tea_openapi import models as open_api_models
        except ImportError as exc:
            raise DNSError("Alibaba Cloud DNS SDK is not installed. Install leet-ssl-cert[aliyun].") from exc

        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
        )
        endpoint = self.settings.get("endpoint")
        if endpoint:
            config.endpoint = endpoint
        return AlidnsClient(config)

    def _client_or_raise(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _import_request(self, name: str) -> Any:
        try:
            from alibabacloud_alidns20150109 import models as alidns_models
        except ImportError as exc:
            raise DNSError("Alibaba Cloud DNS SDK is not installed. Install leet-ssl-cert[aliyun].") from exc
        return getattr(alidns_models, name)

    def _relative_record_name(self, zone: str, record_name: str) -> str:
        normalized = record_name.rstrip(".")
        if normalized == zone:
            return "@"
        suffix = f".{zone}"
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
        return normalized
