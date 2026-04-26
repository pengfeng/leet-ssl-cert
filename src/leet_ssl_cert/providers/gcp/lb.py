"""Google Cloud HTTPS / SSL proxy deployer."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from leet_ssl_cert.errors import DeployError
from leet_ssl_cert.models import DeployResult
from leet_ssl_cert.providers.base import CertificateDeployer
from leet_ssl_cert.providers.gcp.common import (
    extract_resource_name,
    resolve_gcp_project,
)

NAME_PATTERN = re.compile(r"[^a-z0-9-]+")


class GCPLoadBalancerDeployer(CertificateDeployer):
    """Upload self-managed certificates and bind them to GCP target proxies."""

    def validate_credentials(self) -> None:
        project = self._project()
        if self._target_mode() == "https":
            if self._scope() == "regional":
                self._region_target_https_proxies_client().get(
                    project=project,
                    region=self._region(),
                    target_https_proxy=self._target_https_proxy(),
                )
            else:
                self._target_https_proxies_client().get(
                    project=project,
                    target_https_proxy=self._target_https_proxy(),
                )
            return
        self._target_ssl_proxies_client().get(
            project=project,
            target_ssl_proxy=self._target_ssl_proxy(),
        )

    def upload_certificate(self, name: str, cert_pem: str, key_pem: str) -> str:
        project = self._project()
        certificate_name = self._resource_name(name)
        certificate_resource = {
            "name": certificate_name,
            "certificate": cert_pem,
            "private_key": key_pem,
            "description": f"Managed by leet-ssl-cert for {name}",
        }

        if self._scope() == "regional":
            operation = self._region_ssl_certificates_client().insert(
                project=project,
                region=self._region(),
                ssl_certificate_resource=certificate_resource,
            )
        else:
            operation = self._ssl_certificates_client().insert(
                project=project,
                ssl_certificate_resource=certificate_resource,
            )
        self._wait_for_operation(
            operation, action=f"upload certificate {certificate_name}"
        )
        return certificate_name

    def bind_certificate(self, certificate_id: str) -> DeployResult:
        project = self._project()
        certificate_ref = self._certificate_ref(certificate_id)

        if self._target_mode() == "https":
            proxy_name = self._target_https_proxy()
            if self._scope() == "regional":
                client = self._region_target_https_proxies_client()
                current = client.get(
                    project=project,
                    region=self._region(),
                    target_https_proxy=proxy_name,
                )
                old_certificate_id = self._first_certificate(current)
                operation = client.set_ssl_certificates(
                    project=project,
                    region=self._region(),
                    target_https_proxy=proxy_name,
                    region_target_https_proxies_set_ssl_certificates_request_resource={
                        "ssl_certificates": [certificate_ref]
                    },
                )
                bound_to = f"region/{self._region()}/targetHttpsProxy/{proxy_name}"
            else:
                client = self._target_https_proxies_client()
                current = client.get(project=project, target_https_proxy=proxy_name)
                old_certificate_id = self._first_certificate(current)
                operation = client.set_ssl_certificates(
                    project=project,
                    target_https_proxy=proxy_name,
                    target_https_proxies_set_ssl_certificates_request_resource={
                        "ssl_certificates": [certificate_ref]
                    },
                )
                bound_to = f"targetHttpsProxy/{proxy_name}"
            self._wait_for_operation(
                operation, action=f"bind certificate to {bound_to}"
            )
            return DeployResult(
                certificate_id=certificate_id,
                provider="gcp_lb",
                bound_to=bound_to,
                old_certificate_id=old_certificate_id,
            )

        proxy_name = self._target_ssl_proxy()
        client = self._target_ssl_proxies_client()
        current = client.get(project=project, target_ssl_proxy=proxy_name)
        old_certificate_id = self._first_certificate(current)
        operation = client.set_ssl_certificates(
            project=project,
            target_ssl_proxy=proxy_name,
            target_ssl_proxies_set_ssl_certificates_request_resource={
                "ssl_certificates": [certificate_ref]
            },
        )
        bound_to = f"targetSslProxy/{proxy_name}"
        self._wait_for_operation(operation, action=f"bind certificate to {bound_to}")
        return DeployResult(
            certificate_id=certificate_id,
            provider="gcp_lb",
            bound_to=bound_to,
            old_certificate_id=old_certificate_id,
        )

    def cleanup_old_certificates(self, name: str, keep: int = 1) -> list[str]:
        prefix = self._name_prefix(name)
        certificate_names = [
            str(getattr(certificate, "name", "")).strip()
            for certificate in self._list_certificates()
            if str(getattr(certificate, "name", "")).strip().startswith(prefix)
        ]
        certificate_names.sort(reverse=True)

        removed: list[str] = []
        project = self._project()
        for certificate_name in certificate_names[keep:]:
            if self._scope() == "regional":
                operation = self._region_ssl_certificates_client().delete(
                    project=project,
                    region=self._region(),
                    ssl_certificate=certificate_name,
                )
            else:
                operation = self._ssl_certificates_client().delete(
                    project=project,
                    ssl_certificate=certificate_name,
                )
            self._wait_for_operation(
                operation, action=f"delete certificate {certificate_name}"
            )
            removed.append(certificate_name)
        return removed

    def _project(self) -> str:
        project = resolve_gcp_project(self.settings)
        if not project:
            raise DeployError(
                "gcp_lb deployer requires a project: set the 'project' setting, "
                "the GOOGLE_CLOUD_PROJECT env var, or configure Application Default Credentials"
            )
        return project

    def _scope(self) -> str:
        scope = str(self.settings.get("scope", "global")).strip().lower()
        if scope not in {"global", "regional"}:
            raise DeployError("gcp_lb deployer scope must be either global or regional")
        if scope == "regional" and self._target_ssl_proxy():
            raise DeployError(
                "gcp_lb does not support regional target_ssl_proxy bindings"
            )
        return scope

    def _region(self) -> str:
        region = str(self.settings.get("region", "")).strip()
        if self._scope() == "regional" and not region:
            raise DeployError("gcp_lb deployer requires region when scope is regional")
        return region

    def _target_https_proxy(self) -> str:
        return str(self.settings.get("target_https_proxy", "")).strip()

    def _target_ssl_proxy(self) -> str:
        return str(self.settings.get("target_ssl_proxy", "")).strip()

    def _target_mode(self) -> str:
        has_https_proxy = bool(self._target_https_proxy())
        has_ssl_proxy = bool(self._target_ssl_proxy())
        if has_https_proxy and has_ssl_proxy:
            raise DeployError(
                "gcp_lb deployer requires only one of target_https_proxy or target_ssl_proxy"
            )
        if not has_https_proxy and not has_ssl_proxy:
            raise DeployError(
                "gcp_lb deployer requires target_https_proxy or target_ssl_proxy"
            )
        return "https" if has_https_proxy else "ssl"

    def _target_ssl_proxies_client(self) -> Any:
        return self._compute_client("TargetSslProxiesClient")

    def _target_https_proxies_client(self) -> Any:
        return self._compute_client("TargetHttpsProxiesClient")

    def _region_target_https_proxies_client(self) -> Any:
        return self._compute_client("RegionTargetHttpsProxiesClient")

    def _ssl_certificates_client(self) -> Any:
        return self._compute_client("SslCertificatesClient")

    def _region_ssl_certificates_client(self) -> Any:
        return self._compute_client("RegionSslCertificatesClient")

    def _compute_client(self, name: str) -> Any:
        try:
            from google.cloud import compute_v1
        except ImportError as exc:
            raise DeployError(
                "google-cloud-compute is not installed. Install leet-ssl-cert[gcp]."
            ) from exc
        return getattr(compute_v1, name)()

    def _wait_for_operation(self, operation: Any, *, action: str) -> None:
        if operation is None:
            return
        try:
            if hasattr(operation, "result"):
                operation.result(
                    timeout=int(self.settings.get("operation_timeout", 300))
                )
        except Exception as exc:
            raise DeployError(f"GCP operation failed during {action}: {exc}") from exc
        error_code = getattr(operation, "error_code", None)
        if error_code:
            error_message = getattr(operation, "error_message", None) or getattr(
                operation, "http_error_message", None
            )
            raise DeployError(
                f"GCP operation failed during {action}: {error_message or error_code}"
            )

    def _first_certificate(self, proxy: Any) -> str | None:
        ssl_certificates = getattr(proxy, "ssl_certificates", None) or []
        if not ssl_certificates:
            return None
        return extract_resource_name(ssl_certificates[0])

    def _list_certificates(self) -> list[Any]:
        project = self._project()
        if self._scope() == "regional":
            return list(
                self._region_ssl_certificates_client().list(
                    project=project, region=self._region()
                )
            )
        return list(self._ssl_certificates_client().list(project=project))

    def _certificate_ref(self, certificate_name: str) -> str:
        if certificate_name.startswith("https://") or certificate_name.startswith(
            "projects/"
        ):
            return certificate_name
        project = self._project()
        if self._scope() == "regional":
            return (
                f"https://www.googleapis.com/compute/v1/projects/{project}/regions/"
                f"{self._region()}/sslCertificates/{certificate_name}"
            )
        return f"https://www.googleapis.com/compute/v1/projects/{project}/global/sslCertificates/{certificate_name}"

    def _resource_name(self, logical_name: str) -> str:
        normalized = NAME_PATTERN.sub("-", logical_name.lower()).strip("-")
        if not normalized:
            normalized = "cert"
        if not normalized[0].isalpha():
            normalized = f"cert-{normalized}"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        max_base_length = 63 - len("leet--") - len(timestamp)
        normalized = normalized[:max_base_length].rstrip("-") or "cert"
        return f"leet-{normalized}-{timestamp}"

    def _name_prefix(self, logical_name: str) -> str:
        generated = self._resource_name(logical_name)
        return generated.rsplit("-", 1)[0] + "-"
