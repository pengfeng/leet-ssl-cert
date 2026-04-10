"""Provider interfaces for DNS and certificate deployment.

Each cloud provider plugin must implement these interfaces:
- DNSProvider: for ACME DNS-01 challenge management
- CertificateDeployer: for uploading and binding certificates to load balancers
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from leet_ssl_cert.models import DeployResult


class DNSProvider(ABC):
    """Interface for DNS-01 providers.

    Implementations must be able to create and delete TXT records
    and resolve the authoritative zone for a given domain.
    """

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


class CertificateDeployer(ABC):
    """Interface for cloud certificate deployment targets.

    Implementations must be able to upload a certificate, bind it
    to a load balancer or other TLS-terminating resource, and
    clean up old certificates.
    """

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or {}

    def validate_credentials(self) -> None:
        """Validate credentials or connectivity for init/setup flows."""

    @abstractmethod
    def upload_certificate(self, name: str, cert_pem: str, key_pem: str) -> str:
        """Upload a certificate and return the cloud provider certificate id."""

    @abstractmethod
    def bind_certificate(self, certificate_id: str) -> DeployResult:
        """Bind the uploaded certificate to the target resource."""

    @abstractmethod
    def cleanup_old_certificates(self, name: str, keep: int = 1) -> list[str]:
        """Delete older cloud certificates for the logical name."""
