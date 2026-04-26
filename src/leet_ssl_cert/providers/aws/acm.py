"""AWS ACM deployer."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from leet_ssl_cert.errors import DeployError
from leet_ssl_cert.models import DeployResult
from leet_ssl_cert.providers.base import CertificateDeployer

CERT_PATTERN = re.compile(
    r"-----BEGIN CERTIFICATE-----\s+.*?-----END CERTIFICATE-----\s*",
    re.DOTALL,
)


class AWSACMDeployer(CertificateDeployer):
    """Upload certificates to AWS ACM."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        super().__init__(settings=settings)
        self._client: Any | None = None

    def validate_credentials(self) -> None:
        self._client_or_raise().list_certificates(MaxItems=1)

    def upload_certificate(self, name: str, cert_pem: str, key_pem: str) -> str:
        leaf, chain = _split_pem_chain(cert_pem)
        request: dict[str, Any] = {
            "Certificate": leaf.encode("utf-8"),
            "PrivateKey": key_pem.encode("utf-8"),
            "Tags": [
                {"Key": "ManagedBy", "Value": "leet-ssl-cert"},
                {"Key": "Name", "Value": name},
                {"Key": "UploadedAt", "Value": datetime.now(timezone.utc).isoformat()},
            ],
        }
        if chain:
            request["CertificateChain"] = chain.encode("utf-8")
        response = self._client_or_raise().import_certificate(**request)
        certificate_arn = response.get("CertificateArn")
        if not certificate_arn:
            raise DeployError("AWS ACM import succeeded without CertificateArn")
        return certificate_arn

    def bind_certificate(self, certificate_id: str) -> DeployResult:
        region = self._required("region")
        return DeployResult(
            certificate_id=certificate_id,
            provider="aws_acm",
            bound_to=f"acm:{region}",
            old_certificate_id=None,
        )

    def cleanup_old_certificates(self, name: str, keep: int = 1) -> list[str]:
        paginator = self._client_or_raise().get_paginator("list_certificates")
        certificate_arns: list[str] = []
        for page in paginator.paginate(
            CertificateStatuses=["ISSUED", "INACTIVE", "EXPIRED"]
        ):
            for summary in page.get("CertificateSummaryList", []):
                arn = summary.get("CertificateArn")
                if not arn:
                    continue
                tags = (
                    self._client_or_raise()
                    .list_tags_for_certificate(CertificateArn=arn)
                    .get("Tags", [])
                )
                if (
                    _tag_value(tags, "ManagedBy") == "leet-ssl-cert"
                    and _tag_value(tags, "Name") == name
                ):
                    certificate_arns.append(arn)
        certificate_arns.sort(reverse=True)
        deleted: list[str] = []
        for arn in certificate_arns[keep:]:
            self._client_or_raise().delete_certificate(CertificateArn=arn)
            deleted.append(arn)
        return deleted

    def _required(self, key: str) -> str:
        value = str(self.settings.get(key, "")).strip()
        if not value:
            raise DeployError(f"aws_acm deployer requires {key}")
        return value

    def _client_or_raise(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self) -> Any:
        try:
            import boto3
        except ImportError as exc:
            raise DeployError(
                "boto3 is not installed. Install leet-ssl-cert[aws]."
            ) from exc
        session = boto3.session.Session(
            aws_access_key_id=self.settings.get("access_key_id"),
            aws_secret_access_key=self.settings.get("secret_access_key"),
            aws_session_token=self.settings.get("session_token"),
            region_name=self._required("region"),
            profile_name=self.settings.get("profile"),
        )
        return session.client("acm")


def _split_pem_chain(cert_pem: str) -> tuple[str, str | None]:
    matches = CERT_PATTERN.findall(cert_pem)
    if not matches:
        raise DeployError("Certificate PEM did not contain any certificate blocks")
    leaf = matches[0].strip()
    chain = "\n".join(item.strip() for item in matches[1:]).strip()
    return leaf + "\n", (chain + "\n") if chain else None


def _tag_value(tags: list[dict[str, Any]], key: str) -> str | None:
    for tag in tags:
        if tag.get("Key") == key:
            return tag.get("Value")
    return None
