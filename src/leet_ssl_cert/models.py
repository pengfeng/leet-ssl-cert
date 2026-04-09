"""Shared dataclasses used across the package."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class DeployResult:
    """Result returned by a deployer after binding a certificate."""

    certificate_id: str
    provider: str
    bound_to: str
    old_certificate_id: str | None = None


@dataclass(slots=True)
class IssuedCertificate:
    """Certificate material returned by the ACME client."""

    name: str
    domains: list[str]
    certificate_pem: bytes
    private_key_pem: bytes


@dataclass(slots=True)
class IssueResult:
    """High-level issuance outcome for CLI and orchestration reporting."""

    name: str
    action: str
    reason: str | None = None
    cert_path: Path | None = None
    expires_at: datetime | None = None


@dataclass(slots=True)
class DeploymentRecord:
    """High-level deployment outcome for CLI and orchestration reporting."""

    name: str
    provider: str
    certificate_id: str
    bound_to: str
    deleted_certificate_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CertificateStatus:
    """Summary returned by the check command."""

    name: str
    domains: list[str]
    exists_locally: bool
    expires_at: datetime | None
    remaining_days: int | None
    due_for_renewal: bool
    deploy_targets: list[str]
    last_deploy: dict[str, Any]


@dataclass(slots=True)
class RevokeResult:
    """Result returned by certificate revocation."""

    name: str
    revoked: bool


@dataclass(slots=True)
class InitResult:
    """Result returned by the interactive init flow."""

    output_path: Path
    validated: bool
    dns_provider: str
    deployer: str
