"""Top-level orchestration for issue, deploy, run, and check commands."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from .acme_client import AcmeCertificateManager
from .config import AppConfig, CertificateConfig
from .deployer import get_deployer
from .dns import get_dns_provider
from .errors import ACMEError, ConfigError
from .models import CertificateStatus, DeploymentRecord, IssueResult, RevokeResult
from .storage import CertificateStorage, certificate_remaining_days


class CertificateService:
    """Coordinate configuration, ACME issuance, local storage, and deployment."""

    def __init__(
        self,
        config: AppConfig,
        *,
        storage: CertificateStorage | None = None,
        acme_manager: AcmeCertificateManager | None = None,
        dns_factory: Callable[..., object] = get_dns_provider,
        deployer_factory: Callable[..., object] = get_deployer,
    ) -> None:
        self.config = config
        self.storage = storage or CertificateStorage(config.storage.base_dir)
        self.storage.ensure_directories()
        self.acme_manager = acme_manager or AcmeCertificateManager(config, self.storage)
        self.dns_factory = dns_factory
        self.deployer_factory = deployer_factory

    def issue(self, *, name: str | None = None, force: bool = False, dry_run: bool = False) -> list[IssueResult]:
        """Issue or renew selected certificates."""
        results: list[IssueResult] = []
        for certificate in self._select_certificates(name):
            if not force and self.storage.certificate_exists(certificate.name):
                stored = self.storage.load_certificate(certificate.name)
                remaining_days = certificate_remaining_days(stored)
                if remaining_days >= self.config.acme.renewal_days:
                    results.append(
                        IssueResult(
                            name=certificate.name,
                            action="skip",
                            reason=f"{remaining_days} days remaining",
                            cert_path=stored.cert_path,
                            expires_at=stored.certificate.not_valid_after_utc,
                        )
                    )
                    continue

            if dry_run:
                results.append(
                    IssueResult(
                        name=certificate.name,
                        action="dry-run",
                        reason="would issue or renew certificate",
                    )
                )
                continue

            dns_settings = dict(self.config.providers.get(certificate.dns_provider, {}))
            dns_provider = self.dns_factory(certificate.dns_provider, dns_settings)
            issued = self.acme_manager.issue_certificate(certificate, dns_provider)
            stored = self.storage.save_certificate_bundle(
                name=issued.name,
                certificate_pem=issued.certificate_pem,
                private_key_pem=issued.private_key_pem,
                domains=issued.domains,
            )
            results.append(
                IssueResult(
                    name=certificate.name,
                    action="issued",
                    cert_path=stored.cert_path,
                    expires_at=stored.certificate.not_valid_after_utc,
                )
            )
        return results

    def deploy(self, *, name: str | None = None) -> list[DeploymentRecord]:
        """Deploy stored certificates to configured cloud targets."""
        results: list[DeploymentRecord] = []
        for certificate in self._select_certificates(name):
            if not self.storage.certificate_exists(certificate.name):
                raise ACMEError(f"Local certificate bundle not found for {certificate.name}. Run issue first.")
            stored = self.storage.load_certificate(certificate.name)
            for target in certificate.deploy:
                settings = dict(self.config.providers.get(_provider_namespace(target.provider), {}))
                settings.update(target.settings)
                deployer = self.deployer_factory(target.provider, settings)
                certificate_id = deployer.upload_certificate(
                    certificate.name,
                    stored.certificate_pem.decode("utf-8"),
                    stored.private_key_pem.decode("utf-8"),
                )
                deploy_result = deployer.bind_certificate(certificate_id)
                deleted_ids = deployer.cleanup_old_certificates(certificate.name, keep=2)
                self.storage.update_last_deploy(
                    certificate.name,
                    target.provider,
                    {
                        "certificate_id": deploy_result.certificate_id,
                        "deployed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "bound_to": deploy_result.bound_to,
                        "old_certificate_id": deploy_result.old_certificate_id,
                    },
                )
                results.append(
                    DeploymentRecord(
                        name=certificate.name,
                        provider=target.provider,
                        certificate_id=deploy_result.certificate_id,
                        bound_to=deploy_result.bound_to,
                        deleted_certificate_ids=deleted_ids,
                    )
                )
        return results

    def run(self, *, name: str | None = None, force: bool = False, dry_run: bool = False) -> tuple[list[IssueResult], list[DeploymentRecord]]:
        """Run issuance followed by deployment."""
        issue_results = self.issue(name=name, force=force, dry_run=dry_run)
        if dry_run:
            return issue_results, []
        return issue_results, self.deploy(name=name)

    def check(self, *, name: str | None = None) -> list[CertificateStatus]:
        """Return local status for all configured certificates."""
        statuses: list[CertificateStatus] = []
        for certificate in self._select_certificates(name):
            if self.storage.certificate_exists(certificate.name):
                stored = self.storage.load_certificate(certificate.name)
                remaining_days = certificate_remaining_days(stored)
                expires_at = stored.certificate.not_valid_after_utc
                last_deploy = stored.metadata.get("last_deploy", {})
                exists_locally = True
            else:
                remaining_days = None
                expires_at = None
                last_deploy = {}
                exists_locally = False
            due = not exists_locally or remaining_days is None or remaining_days < self.config.acme.renewal_days
            statuses.append(
                CertificateStatus(
                    name=certificate.name,
                    domains=certificate.domains,
                    exists_locally=exists_locally,
                    expires_at=expires_at,
                    remaining_days=remaining_days,
                    due_for_renewal=due,
                    deploy_targets=[target.provider for target in certificate.deploy],
                    last_deploy=last_deploy,
                )
            )
        return statuses

    def _select_certificates(self, name: str | None) -> list[CertificateConfig]:
        if name is None:
            return self.config.certificates
        selected = [certificate for certificate in self.config.certificates if certificate.name == name]
        if not selected:
            raise ConfigError(f"Unknown certificate name: {name}")
        return selected

    def revoke(self, *, name: str) -> RevokeResult:
        """Revoke a locally stored certificate via ACME."""
        self._select_certificates(name)
        if not self.storage.certificate_exists(name):
            raise ACMEError(f"Local certificate bundle not found for {name}. Nothing to revoke.")
        stored = self.storage.load_certificate(name)
        self.acme_manager.revoke_certificate(stored)
        return RevokeResult(name=name, revoked=True)


def _provider_namespace(provider_name: str) -> str:
    if "_" not in provider_name:
        return provider_name
    return provider_name.split("_", 1)[0]
