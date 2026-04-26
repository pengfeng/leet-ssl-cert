"""Local certificate and metadata storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from cryptography import x509


@dataclass(slots=True)
class StoredCertificate:
    """On-disk certificate bundle."""

    name: str
    directory: Path
    key_path: Path
    cert_path: Path
    meta_path: Path
    private_key_pem: bytes
    certificate_pem: bytes
    metadata: dict[str, Any]

    @property
    def certificate(self) -> x509.Certificate:
        return x509.load_pem_x509_certificate(self.certificate_pem)


class CertificateStorage:
    """Manage account keys, local certificate files, and metadata."""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir).expanduser()
        self.state_dir = self.base_dir.parent

    @property
    def account_key_path(self) -> Path:
        return self.state_dir / "account.key"

    def ensure_directories(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def cert_dir(self, name: str) -> Path:
        return self.base_dir / name

    def key_path(self, name: str) -> Path:
        return self.cert_dir(name) / f"{name}.key"

    def cert_path(self, name: str) -> Path:
        return self.cert_dir(name) / f"{name}.pem"

    def meta_path(self, name: str) -> Path:
        return self.cert_dir(name) / f"{name}.meta.json"

    def load_account_key_pem(self) -> bytes | None:
        if not self.account_key_path.exists():
            return None
        return self.account_key_path.read_bytes()

    def save_account_key_pem(self, pem: bytes) -> Path:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.account_key_path, pem, mode=0o600)
        return self.account_key_path

    def certificate_exists(self, name: str) -> bool:
        return self.cert_path(name).exists() and self.key_path(name).exists()

    def load_private_key_pem(self, name: str) -> bytes | None:
        key_path = self.key_path(name)
        if not key_path.exists():
            return None
        return key_path.read_bytes()

    def load_certificate(self, name: str) -> StoredCertificate:
        cert_path = self.cert_path(name)
        key_path = self.key_path(name)
        meta_path = self.meta_path(name)
        if not cert_path.exists() or not key_path.exists() or not meta_path.exists():
            raise FileNotFoundError(f"Stored certificate bundle missing for {name}")
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        return StoredCertificate(
            name=name,
            directory=self.cert_dir(name),
            key_path=key_path,
            cert_path=cert_path,
            meta_path=meta_path,
            private_key_pem=key_path.read_bytes(),
            certificate_pem=cert_path.read_bytes(),
            metadata=metadata,
        )

    def save_certificate_bundle(
        self,
        *,
        name: str,
        certificate_pem: bytes,
        private_key_pem: bytes,
        domains: list[str],
    ) -> StoredCertificate:
        certificate = x509.load_pem_x509_certificate(certificate_pem)
        cert_dir = self.cert_dir(name)
        cert_dir.mkdir(parents=True, exist_ok=True)

        metadata = self._build_metadata(
            domains, certificate, self._read_metadata_if_exists(name)
        )
        self._atomic_write(self.key_path(name), private_key_pem, mode=0o600)
        self._atomic_write(self.cert_path(name), certificate_pem, mode=0o600)
        self._atomic_write(
            self.meta_path(name),
            json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8"),
            mode=0o600,
        )
        return self.load_certificate(name)

    def update_last_deploy(
        self, name: str, provider: str, details: dict[str, Any]
    ) -> None:
        metadata = self._read_metadata_if_exists(name)
        last_deploy = metadata.setdefault("last_deploy", {})
        last_deploy[provider] = details
        self._atomic_write(
            self.meta_path(name),
            json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8"),
            mode=0o600,
        )

    def read_metadata(self, name: str) -> dict[str, Any]:
        return self._read_metadata_if_exists(name)

    def _read_metadata_if_exists(self, name: str) -> dict[str, Any]:
        meta_path = self.meta_path(name)
        if not meta_path.exists():
            return {}
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def _build_metadata(
        self,
        domains: list[str],
        certificate: x509.Certificate,
        existing: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = {
            "domains": domains,
            "not_before": _isoformat(certificate.not_valid_before_utc),
            "not_after": _isoformat(certificate.not_valid_after_utc),
            "serial": format(certificate.serial_number, "x"),
            "last_deploy": existing.get("last_deploy", {}),
        }
        return metadata

    def _atomic_write(self, path: Path, content: bytes, mode: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            handle.write(content)
            temp_name = handle.name
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)


def certificate_remaining_days(
    stored: StoredCertificate, now: datetime | None = None
) -> int:
    """Return whole remaining days until certificate expiry."""
    current = now or datetime.now(timezone.utc)
    delta = stored.certificate.not_valid_after_utc - current
    return max(int(delta.total_seconds() // 86400), 0)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
