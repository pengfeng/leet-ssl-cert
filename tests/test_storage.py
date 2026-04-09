from __future__ import annotations

from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from datetime import datetime, timedelta, timezone

from leet_ssl_cert.storage import CertificateStorage


def test_save_and_load_certificate_bundle(tmp_path: Path) -> None:
    storage = CertificateStorage(tmp_path / "certs")
    certificate_pem, private_key_pem = build_self_signed_cert()

    stored = storage.save_certificate_bundle(
        name="site",
        certificate_pem=certificate_pem,
        private_key_pem=private_key_pem,
        domains=["example.com"],
    )

    reloaded = storage.load_certificate("site")

    assert stored.cert_path.exists()
    assert reloaded.metadata["domains"] == ["example.com"]
    assert reloaded.certificate.serial_number > 0


def build_self_signed_cert() -> tuple[bytes, bytes]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "example.com")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=5))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=90))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("example.com")]), critical=False)
        .sign(private_key, hashes.SHA256())
    )
    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    key_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    return cert_pem, key_pem
