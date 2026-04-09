"""ACME protocol implementation for issuance and revocation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import time
from typing import Any

from acme import client as acme_client
from acme import crypto_util, errors as acme_errors, messages
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import dns.exception
import dns.resolver
import josepy as jose

from .config import AcmeConfig, AppConfig, CertificateConfig
from .dns.base import DNSProvider
from .errors import ACMEError, DNSError
from .models import IssuedCertificate
from .storage import CertificateStorage, StoredCertificate


@dataclass(slots=True)
class ChallengeRecord:
    zone: str
    record_name: str
    value: str


class AcmeCertificateManager:
    """Handle ACME account registration, issuance, polling, and revocation."""

    def __init__(
        self,
        config: AppConfig,
        storage: CertificateStorage,
        *,
        resolver: dns.resolver.Resolver | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self.config = config
        self.acme = config.acme
        self.storage = storage
        self.resolver = resolver or dns.resolver.Resolver()
        self.sleep = sleep

    def issue_certificate(self, certificate: CertificateConfig, dns_provider: DNSProvider) -> IssuedCertificate:
        """Issue or renew a certificate using DNS-01 validation."""
        account_key = self._load_or_create_account_key()
        client = self._connect_client(account_key)
        private_key_pem = self.storage.load_private_key_pem(certificate.name) or self._generate_private_key_pem(
            self.acme.key_size
        )
        csr_pem = crypto_util.make_csr(private_key_pem, domains=certificate.domains)
        order = client.new_order(csr_pem)

        challenge_records: list[ChallengeRecord] = []
        original_error: Exception | None = None
        try:
            for authorization in order.authorizations:
                identifier = authorization.body.identifier
                domain = identifier.value
                challenge_body = self._select_dns_challenge(authorization.body.challenges)
                response, validation = challenge_body.chall.response_and_validation(account_key)
                zone = dns_provider.find_zone_for_domain(domain)
                record_name = f"_acme-challenge.{domain}"
                dns_provider.create_txt_record(zone, record_name, validation)
                challenge_records.append(ChallengeRecord(zone=zone, record_name=record_name, value=validation))
                self._wait_for_dns(record_name, validation)
                client.answer_challenge(challenge_body, response)

            deadline = datetime.now(timezone.utc) + timedelta(seconds=self.acme.order_poll_timeout)
            finalized = client.poll_and_finalize(order, deadline)
            if not finalized.fullchain_pem:
                raise ACMEError(f"ACME order for {certificate.name} did not return a certificate chain")
            return IssuedCertificate(
                name=certificate.name,
                domains=certificate.domains,
                certificate_pem=finalized.fullchain_pem.encode("utf-8"),
                private_key_pem=private_key_pem,
            )
        except DNSError as exc:
            original_error = exc
            raise
        except acme_errors.Error as exc:
            original_error = exc
            raise ACMEError(f"ACME issuance failed for {certificate.name}: {exc}") from exc
        except Exception as exc:
            original_error = exc
            raise ACMEError(f"Unexpected ACME failure for {certificate.name}: {exc}") from exc
        finally:
            cleanup_error = self._cleanup_challenge_records(dns_provider, challenge_records)
            if cleanup_error is not None:
                if original_error is not None:
                    try:
                        original_error.add_note(str(cleanup_error))
                    except AttributeError:
                        pass
                else:
                    raise cleanup_error

    def revoke_certificate(self, stored: StoredCertificate, reason: int = 0) -> None:
        """Revoke a locally stored certificate through ACME."""
        account_key = self._load_or_create_account_key()
        client = self._connect_client(account_key)
        certificate = x509.load_pem_x509_certificate(stored.certificate_pem)
        try:
            client.revoke(certificate, reason)
        except acme_errors.Error as exc:
            raise ACMEError(f"Failed to revoke certificate {stored.name}: {exc}") from exc

    def _connect_client(self, account_key: jose.JWKRSA) -> acme_client.ClientV2:
        network = acme_client.ClientNetwork(key=account_key, user_agent="leet-ssl-cert/0.1.0")
        directory = acme_client.ClientV2.get_directory(self.acme.directory_url, network)
        client = acme_client.ClientV2(directory, network)
        registration = messages.NewRegistration.from_data(
            email=self.config.account.email,
            terms_of_service_agreed=True,
        )
        try:
            client.new_account(registration)
        except acme_errors.ConflictError as exc:
            existing = messages.RegistrationResource(
                body=messages.Registration.from_data(
                    email=self.config.account.email,
                    terms_of_service_agreed=True,
                ),
                uri=exc.location,
            )
            client.net.account = client.query_registration(existing)
        return client

    def _load_or_create_account_key(self) -> jose.JWKRSA:
        pem = self.storage.load_account_key_pem()
        if pem is None:
            pem = self._generate_private_key_pem(4096)
            self.storage.save_account_key_pem(pem)
        private_key = serialization.load_pem_private_key(pem, password=None)
        return jose.JWKRSA(key=private_key)

    def _generate_private_key_pem(self, key_size: int) -> bytes:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
        return private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def _select_dns_challenge(self, challenges: list[Any]) -> Any:
        for challenge in challenges:
            if getattr(challenge.chall, "typ", None) == "dns-01":
                return challenge
        raise ACMEError("ACME server did not offer a dns-01 challenge")

    def _wait_for_dns(self, record_name: str, expected_value: str) -> None:
        attempts = self.acme.dns_poll_attempts
        interval = self.acme.dns_poll_interval
        fqdn = record_name.rstrip(".")
        for attempt in range(attempts):
            try:
                answers = self.resolver.resolve(fqdn, "TXT")
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout):
                answers = []
            values = {self._normalize_txt_value(answer) for answer in answers}
            if expected_value in values:
                return
            if attempt < attempts - 1:
                self.sleep(interval)
        raise DNSError(f"TXT record {fqdn} did not propagate in time")

    def _normalize_txt_value(self, answer: Any) -> str:
        strings = getattr(answer, "strings", None)
        if strings:
            return b"".join(strings).decode("utf-8")
        text = answer.to_text()
        return text.strip('"')

    def _cleanup_challenge_records(self, dns_provider: DNSProvider, records: list[ChallengeRecord]) -> DNSError | None:
        errors: list[str] = []
        for record in reversed(records):
            try:
                dns_provider.delete_txt_record(record.zone, record.record_name, record.value)
            except Exception as exc:  # pragma: no cover - cleanup best effort
                errors.append(f"{record.record_name}: {exc}")
        if errors:
            return DNSError("Failed to clean up DNS challenge records: " + "; ".join(errors))
        return None
