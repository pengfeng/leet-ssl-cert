from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from leet_ssl_cert.config import (
    AccountConfig,
    AcmeConfig,
    AppConfig,
    CertificateConfig,
    DeployTargetConfig,
    StorageConfig,
)
from leet_ssl_cert.errors import DeployError
from leet_ssl_cert.models import DeployResult, IssuedCertificate
from leet_ssl_cert.service import CertificateService
from leet_ssl_cert.storage import CertificateStorage


class FakeAcmeManager:
    def __init__(self) -> None:
        self.revoked_names: list[str] = []

    def issue_certificate(self, certificate: CertificateConfig, dns_provider: object) -> IssuedCertificate:
        cert_pem, key_pem = build_self_signed_cert(certificate.domains[0], days=20)
        return IssuedCertificate(
            name=certificate.name,
            domains=certificate.domains,
            certificate_pem=cert_pem,
            private_key_pem=key_pem,
        )

    def revoke_certificate(self, stored) -> None:
        self.revoked_names.append(stored.name)


class FakeDeployer:
    def __init__(self, settings: dict[str, object] | None = None) -> None:
        self.settings = settings or {}

    def upload_certificate(self, name: str, cert_pem: str, key_pem: str) -> str:
        return f"cert-{name}"

    def bind_certificate(self, certificate_id: str) -> DeployResult:
        return DeployResult(
            certificate_id=certificate_id,
            provider="aliyun_clb",
            bound_to="lb-123:443",
            old_certificate_id="old-cert",
        )

    def cleanup_old_certificates(self, name: str, keep: int = 1) -> list[str]:
        return ["old-cert"]


def test_issue_and_deploy_round_trip(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    storage = CertificateStorage(config.storage.base_dir)
    acme_manager = FakeAcmeManager()
    service = CertificateService(
        config,
        storage=storage,
        acme_manager=acme_manager,
        dns_factory=lambda name, settings: object(),
        deployer_factory=lambda name, settings: FakeDeployer(settings),
    )

    issue_results = service.issue()
    deploy_results = service.deploy()
    check_results = service.check()

    assert issue_results[0].action == "issued"
    assert deploy_results[0].certificate_id == "cert-site"
    assert check_results[0].exists_locally is True
    assert "aliyun_clb" in check_results[0].last_deploy


def test_issue_skips_certificate_when_not_due(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    storage = CertificateStorage(config.storage.base_dir)
    cert_pem, key_pem = build_self_signed_cert("example.com", days=90)
    storage.save_certificate_bundle(
        name="site",
        certificate_pem=cert_pem,
        private_key_pem=key_pem,
        domains=["example.com"],
    )
    service = CertificateService(
        config,
        storage=storage,
        acme_manager=FakeAcmeManager(),
        dns_factory=lambda name, settings: object(),
        deployer_factory=lambda name, settings: FakeDeployer(settings),
    )

    issue_results = service.issue()

    assert issue_results[0].action == "skip"
    assert "days remaining" in (issue_results[0].reason or "")


def test_revoke_calls_acme_manager(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    storage = CertificateStorage(config.storage.base_dir)
    cert_pem, key_pem = build_self_signed_cert("example.com", days=90)
    storage.save_certificate_bundle(
        name="site",
        certificate_pem=cert_pem,
        private_key_pem=key_pem,
        domains=["example.com"],
    )
    acme_manager = FakeAcmeManager()
    service = CertificateService(
        config,
        storage=storage,
        acme_manager=acme_manager,
        dns_factory=lambda name, settings: object(),
        deployer_factory=lambda name, settings: FakeDeployer(settings),
    )

    result = service.revoke(name="site")

    assert result.revoked is True
    assert acme_manager.revoked_names == ["site"]


def test_deploy_uses_aws_provider_namespace(tmp_path: Path) -> None:
    captured_settings: list[dict[str, object]] = []

    class CapturingDeployer(FakeDeployer):
        def __init__(self, settings: dict[str, object] | None = None) -> None:
            super().__init__(settings)
            captured_settings.append(self.settings)

    config = AppConfig(
        account=AccountConfig(email="admin@example.com"),
        acme=AcmeConfig(renewal_days=30),
        storage=StorageConfig(base_dir=tmp_path / "state" / "certs"),
        certificates=[
            CertificateConfig(
                name="site",
                domains=["example.com"],
                dns_provider="aws",
                deploy=[DeployTargetConfig(provider="aws_acm", settings={"region": "us-east-1"})],
            )
        ],
        providers={"aws": {"profile": "default"}},
        path=tmp_path / "config.yaml",
    )
    storage = CertificateStorage(config.storage.base_dir)
    cert_pem, key_pem = build_self_signed_cert("example.com", days=90)
    storage.save_certificate_bundle(
        name="site",
        certificate_pem=cert_pem,
        private_key_pem=key_pem,
        domains=["example.com"],
    )
    service = CertificateService(
        config,
        storage=storage,
        acme_manager=FakeAcmeManager(),
        dns_factory=lambda name, settings: object(),
        deployer_factory=lambda name, settings: CapturingDeployer(settings),
    )

    service.deploy()

    assert captured_settings[0]["profile"] == "default"
    assert captured_settings[0]["region"] == "us-east-1"


def test_deploy_wraps_provider_exceptions(tmp_path: Path) -> None:
    class FailingDeployer(FakeDeployer):
        def upload_certificate(self, name: str, cert_pem: str, key_pem: str) -> str:
            raise RuntimeError("Connection reset by peer")

    config = build_config(tmp_path)
    storage = CertificateStorage(config.storage.base_dir)
    cert_pem, key_pem = build_self_signed_cert("example.com", days=90)
    storage.save_certificate_bundle(
        name="site",
        certificate_pem=cert_pem,
        private_key_pem=key_pem,
        domains=["example.com"],
    )
    service = CertificateService(
        config,
        storage=storage,
        acme_manager=FakeAcmeManager(),
        dns_factory=lambda name, settings: object(),
        deployer_factory=lambda name, settings: FailingDeployer(settings),
    )

    with pytest.raises(DeployError, match="Deploy failed for site via aliyun_clb"):
        service.deploy()


def build_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        account=AccountConfig(email="admin@example.com"),
        acme=AcmeConfig(renewal_days=30),
        storage=StorageConfig(base_dir=tmp_path / "state" / "certs"),
        certificates=[
            CertificateConfig(
                name="site",
                domains=["example.com"],
                dns_provider="aliyun",
                deploy=[
                    DeployTargetConfig(
                        provider="aliyun_clb",
                        settings={"load_balancer_id": "lb-123", "listener_port": 443},
                    )
                ],
            )
        ],
        providers={"aliyun": {"access_key_id": "ak", "access_key_secret": "sk"}},
        path=tmp_path / "config.yaml",
    )


def build_self_signed_cert(common_name: str, *, days: int) -> tuple[bytes, bytes]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=5))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(common_name)]), critical=False)
        .sign(private_key, hashes.SHA256())
    )
    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    key_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    return cert_pem, key_pem
