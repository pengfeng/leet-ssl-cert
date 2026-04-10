"""Provider registry for DNS and deployment plugins.

Each provider package (e.g. providers.aliyun, providers.aws) registers
its implementations at import time. The registry functions below are
used by the rest of the application to instantiate providers by name.
"""

from __future__ import annotations

from typing import Any

from leet_ssl_cert.errors import ConfigError

from leet_ssl_cert.providers.base import CertificateDeployer, DNSProvider

DNS_PROVIDER_REGISTRY: dict[str, type[DNSProvider]] = {}
DEPLOYER_REGISTRY: dict[str, type[CertificateDeployer]] = {}


def register_dns_provider(name: str, provider_cls: type[DNSProvider]) -> None:
    """Register a DNS provider implementation by name."""
    DNS_PROVIDER_REGISTRY[name] = provider_cls


def register_deployer(name: str, deployer_cls: type[CertificateDeployer]) -> None:
    """Register a deployer implementation by name."""
    DEPLOYER_REGISTRY[name] = deployer_cls


def get_dns_provider(name: str, settings: dict[str, Any] | None = None) -> DNSProvider:
    """Instantiate a configured DNS provider by registry name."""
    try:
        provider_cls = DNS_PROVIDER_REGISTRY[name]
    except KeyError as exc:
        raise ConfigError(f"Unsupported DNS provider: {name}") from exc
    return provider_cls(settings=settings)


def get_deployer(name: str, settings: dict[str, Any] | None = None) -> CertificateDeployer:
    """Instantiate a deployer by registry name."""
    try:
        deployer_cls = DEPLOYER_REGISTRY[name]
    except KeyError as exc:
        raise ConfigError(f"Unsupported deployer: {name}") from exc
    return deployer_cls(settings=settings)


# Import provider packages to trigger registration.
import leet_ssl_cert.providers.aliyun  # noqa: E402, F401
import leet_ssl_cert.providers.aws  # noqa: E402, F401
