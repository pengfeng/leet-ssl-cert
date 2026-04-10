"""DNS provider abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..errors import ConfigError

DNS_PROVIDER_REGISTRY: dict[str, type["DNSProvider"]] = {}


class DNSProvider(ABC):
    """Interface for DNS-01 providers."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or {}

    def validate_credentials(self) -> None:
        """Validate credentials or connectivity for init/setup flows."""

    @abstractmethod
    def create_txt_record(self, zone: str, record_name: str, value: str) -> None:
        """Create a TXT record for ACME DNS validation."""

    @abstractmethod
    def delete_txt_record(self, zone: str, record_name: str, value: str) -> None:
        """Delete a TXT record after validation completes."""

    @abstractmethod
    def find_zone_for_domain(self, domain: str) -> str:
        """Resolve the authoritative zone for a requested domain."""


def register_dns_provider(name: str, provider_cls: type[DNSProvider]) -> None:
    """Register a DNS provider implementation by name."""
    DNS_PROVIDER_REGISTRY[name] = provider_cls


def get_dns_provider(name: str, settings: dict[str, Any] | None = None) -> DNSProvider:
    """Instantiate a configured DNS provider."""
    try:
        provider_cls = DNS_PROVIDER_REGISTRY[name]
    except KeyError as exc:
        raise ConfigError(f"Unsupported DNS provider: {name}") from exc
    return provider_cls(settings=settings)
