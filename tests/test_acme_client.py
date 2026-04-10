from __future__ import annotations

from pathlib import Path

from leet_ssl_cert.acme_client import AcmeCertificateManager
from leet_ssl_cert.config import AccountConfig, AcmeConfig, AppConfig, StorageConfig
from leet_ssl_cert.storage import CertificateStorage


def test_order_poll_deadline_is_naive(tmp_path: Path) -> None:
    manager = AcmeCertificateManager(
        AppConfig(
            account=AccountConfig(email="admin@example.com"),
            acme=AcmeConfig(order_poll_timeout=30),
            storage=StorageConfig(base_dir=tmp_path / "certs"),
            certificates=[],
            providers={},
            path=tmp_path / "config.yaml",
        ),
        CertificateStorage(tmp_path / "certs"),
    )

    deadline = manager._order_poll_deadline()

    assert deadline.tzinfo is None
