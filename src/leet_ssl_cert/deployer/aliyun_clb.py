"""Alibaba Cloud CLB deployer."""

from __future__ import annotations

from datetime import datetime, timezone
import os
import re
from typing import Any

from ..errors import DeployError
from ..models import DeployResult
from .base import CertificateDeployer

CERT_PATTERN = re.compile(
    r"-----BEGIN CERTIFICATE-----\s+.*?-----END CERTIFICATE-----\s*",
    re.DOTALL,
)


class AliyunCLBDeployer(CertificateDeployer):
    """Upload and bind certificates to Alibaba Cloud CLB listeners."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        super().__init__(settings=settings)
        self._client: Any | None = None

    def validate_credentials(self) -> None:
        request_cls = self._import_request("DescribeServerCertificatesRequest")
        try:
            self._client_or_raise().describe_server_certificates(request_cls(region_id=self._region_id()))
        except DeployError:
            raise
        except Exception as exc:
            raise DeployError(f"Alibaba Cloud CLB credential validation failed: {exc}") from exc

    def upload_certificate(self, name: str, cert_pem: str, key_pem: str) -> str:
        request_cls = self._import_request("UploadServerCertificateRequest")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        request = request_cls(
            region_id=self._region_id(),
            server_certificate_name=f"leet-{name}-{timestamp}",
            server_certificate=_leaf_certificate_pem(cert_pem),
            private_key=key_pem,
        )
        response = self._client_or_raise().upload_server_certificate(request)
        certificate_id = getattr(getattr(response, "body", response), "server_certificate_id", None)
        if not certificate_id:
            raise DeployError("Alibaba Cloud CLB upload succeeded without returning server_certificate_id")
        return certificate_id

    def bind_certificate(self, certificate_id: str) -> DeployResult:
        load_balancer_id = self._required("load_balancer_id")
        listener_port = int(self._required("listener_port"))
        old_certificate_id = self._get_existing_certificate_id(load_balancer_id, listener_port)

        request_cls = self._import_request("SetLoadBalancerHTTPSListenerAttributeRequest")
        request = request_cls(
            region_id=self._region_id(),
            load_balancer_id=load_balancer_id,
            listener_port=listener_port,
            server_certificate_id=certificate_id,
        )
        self._client_or_raise().set_load_balancer_https_listener_attribute(request)
        return DeployResult(
            certificate_id=certificate_id,
            provider="aliyun_clb",
            bound_to=f"{load_balancer_id}:{listener_port}",
            old_certificate_id=old_certificate_id,
        )

    def cleanup_old_certificates(self, name: str, keep: int = 1) -> list[str]:
        request_cls = self._import_request("DescribeServerCertificatesRequest")
        response = self._client_or_raise().describe_server_certificates(request_cls(region_id=self._region_id()))
        records = getattr(getattr(response.body, "server_certificates", None), "server_certificate", []) or []
        prefix = f"leet-{name}-"
        matching = [record for record in records if str(getattr(record, "server_certificate_name", "")).startswith(prefix)]
        matching.sort(key=lambda item: str(getattr(item, "server_certificate_name", "")), reverse=True)

        deleted_ids: list[str] = []
        delete_request_cls = self._import_request("DeleteServerCertificateRequest")
        for record in matching[keep:]:
            certificate_id = getattr(record, "server_certificate_id", None)
            if not certificate_id:
                continue
            self._client_or_raise().delete_server_certificate(
                delete_request_cls(region_id=self._region_id(), server_certificate_id=certificate_id)
            )
            deleted_ids.append(certificate_id)
        return deleted_ids

    def _get_existing_certificate_id(self, load_balancer_id: str, listener_port: int) -> str | None:
        request_cls = self._import_request("DescribeLoadBalancerHTTPSListenerAttributeRequest")
        response = self._client_or_raise().describe_load_balancer_https_listener_attribute(
            request_cls(region_id=self._region_id(), load_balancer_id=load_balancer_id, listener_port=listener_port)
        )
        return getattr(getattr(response, "body", response), "server_certificate_id", None)

    def _required(self, key: str) -> Any:
        if key not in self.settings or self.settings[key] in (None, ""):
            raise DeployError(f"aliyun_clb deployer requires {key}")
        return self.settings[key]

    def _build_client(self) -> Any:
        access_key_id = self.settings.get("access_key_id")
        access_key_secret = self.settings.get("access_key_secret")
        if not access_key_id or not access_key_secret:
            raise DeployError("aliyun_clb deployer requires access_key_id and access_key_secret")
        try:
            from alibabacloud_slb20140515.client import Client as SlbClient
            from alibabacloud_tea_openapi import models as open_api_models
        except ImportError as exc:
            raise DeployError("Alibaba Cloud SLB SDK is not installed. Install leet-ssl-cert[aliyun].") from exc

        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            region_id=self._region_id(),
        )
        endpoint = self.settings.get("endpoint")
        if endpoint:
            config.endpoint = endpoint
        return SlbClient(config)

    def _region_id(self) -> str:
        region_id = str(self.settings.get("region") or os.getenv("ALICLOUD_REGION") or "").strip()
        if not region_id:
            raise DeployError("aliyun_clb deployer requires region or ALICLOUD_REGION")
        return region_id

    def _import_request(self, name: str) -> Any:
        try:
            from alibabacloud_slb20140515 import models as slb_models
        except ImportError as exc:
            raise DeployError("Alibaba Cloud SLB SDK is not installed. Install leet-ssl-cert[aliyun].") from exc
        return getattr(slb_models, name)

    def _client_or_raise(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client


def _leaf_certificate_pem(cert_pem: str) -> str:
    matches = CERT_PATTERN.findall(cert_pem)
    if not matches:
        raise DeployError("Certificate PEM did not contain any certificate blocks")
    return matches[0].strip() + "\n"
