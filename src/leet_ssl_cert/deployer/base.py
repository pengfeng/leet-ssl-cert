"""Certificate deployer abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..errors import ConfigError
from ..models import DeployResult

DEPLOYER_REGISTRY: dict[str, type["CertificateDeployer"]] = {}


class CertificateDeployer(ABC):
    """Interface for cloud certificate deployment targets."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or {}

    @abstractmethod
    def upload_certificate(self, name: str, cert_pem: str, key_pem: str) -> str:
        """Upload a certificate and return the cloud provider certificate id."""

    @abstractmethod
    def bind_certificate(self, certificate_id: str) -> DeployResult:
        """Bind the uploaded certificate to the target resource."""

    @abstractmethod
    def cleanup_old_certificates(self, name: str, keep: int = 1) -> list[str]:
        """Delete older cloud certificates for the logical name."""


def register_deployer(name: str, deployer_cls: type[CertificateDeployer]) -> None:
    """Register a deployer by name."""
    DEPLOYER_REGISTRY[name] = deployer_cls


def get_deployer(name: str, settings: dict[str, Any] | None = None) -> CertificateDeployer:
    """Instantiate a deployer by registry name."""
    try:
        deployer_cls = DEPLOYER_REGISTRY[name]
    except KeyError as exc:
        raise ConfigError(f"Unsupported deployer: {name}") from exc
    return deployer_cls(settings=settings)
