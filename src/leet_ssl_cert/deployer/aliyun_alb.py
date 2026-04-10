"""Alibaba Cloud ALB deployer."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any

from ..errors import DeployError
from ..models import DeployResult
from .base import CertificateDeployer


class AliyunALBDeployer(CertificateDeployer):
    """Upload certificates to Alibaba CAS and bind them to an ALB listener."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        super().__init__(settings=settings)
        self._alb_client: Any | None = None
        self._cas_client: Any | None = None

    def validate_credentials(self) -> None:
        try:
            self._cas_client_or_raise().list_user_certificate_order(
                self._cas_request("ListUserCertificateOrderRequest")(show_size=1, current_page=1, order_type="UPLOAD")
            )
            self._alb_client_or_raise().list_listeners(self._alb_request("ListListenersRequest")(max_results=1))
        except DeployError:
            raise
        except Exception as exc:
            raise DeployError(f"Alibaba Cloud ALB credential validation failed: {exc}") from exc

    def upload_certificate(self, name: str, cert_pem: str, key_pem: str) -> str:
        request_cls = self._cas_request("UploadUserCertificateRequest")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        response = self._cas_client_or_raise().upload_user_certificate(
            request_cls(
                name=f"leet-{name}-{timestamp}",
                cert=cert_pem,
                key=key_pem,
            )
        )
        certificate_id = getattr(getattr(response, "body", response), "cert_id", None)
        if certificate_id is None:
            certificate_id = getattr(getattr(response, "body", response), "CertId", None)
        if certificate_id is None:
            raise DeployError("Alibaba CAS upload succeeded without returning CertId")
        return str(certificate_id)

    def bind_certificate(self, certificate_id: str) -> DeployResult:
        listener_id = self._required("listener_id")
        old_certificate_id = self._current_listener_certificate(listener_id)
        certificates = [{"CertificateId": certificate_id}]
        request_cls = self._alb_request("AssociateAdditionalCertificatesWithListenerRequest")
        self._alb_client_or_raise().associate_additional_certificates_with_listener(
            request_cls(listener_id=listener_id, certificates=certificates)
        )
        return DeployResult(
            certificate_id=certificate_id,
            provider="aliyun_alb",
            bound_to=listener_id,
            old_certificate_id=old_certificate_id,
        )

    def cleanup_old_certificates(self, name: str, keep: int = 1) -> list[str]:
        request_cls = self._cas_request("ListUserCertificateOrderRequest")
        response = self._cas_client_or_raise().list_user_certificate_order(
            request_cls(show_size=100, current_page=1, order_type="UPLOAD")
        )
        records = getattr(getattr(response.body, "certificate_order_list", None), "certificate_order_list", []) or []
        prefix = f"leet-{name}-"
        matching = [record for record in records if str(getattr(record, "name", "")).startswith(prefix)]
        matching.sort(key=lambda item: str(getattr(item, "name", "")), reverse=True)

        deleted: list[str] = []
        delete_request_cls = self._cas_request("DeleteUserCertificateRequest")
        listener_id = self._required("listener_id")
        for record in matching[keep:]:
            cert_id = getattr(record, "cert_id", None) or getattr(record, "certificate_id", None)
            if cert_id is None:
                continue
            cert_id = str(cert_id)
            try:
                self._alb_client_or_raise().dissociate_additional_certificates_from_listener(
                    self._alb_request("DissociateAdditionalCertificatesFromListenerRequest")(
                        listener_id=listener_id,
                        certificates=[{"CertificateId": cert_id}],
                    )
                )
            except Exception:
                pass
            self._cas_client_or_raise().delete_user_certificate(delete_request_cls(cert_id=cert_id))
            deleted.append(cert_id)
        return deleted

    def _current_listener_certificate(self, listener_id: str) -> str | None:
        request_cls = self._alb_request("ListListenerCertificatesRequest")
        response = self._alb_client_or_raise().list_listener_certificates(request_cls(listener_id=listener_id))
        certificates = getattr(getattr(response.body, "certificates", None), "certificates", []) or []
        for certificate in certificates:
            cert_id = getattr(certificate, "certificate_id", None)
            if cert_id is not None:
                return str(cert_id)
        return None

    def _required(self, key: str) -> str:
        value = str(self.settings.get(key, "")).strip()
        if not value:
            raise DeployError(f"aliyun_alb deployer requires {key}")
        return value

    def _alb_client_or_raise(self) -> Any:
        if self._alb_client is None:
            self._alb_client = self._build_alb_client()
        return self._alb_client

    def _cas_client_or_raise(self) -> Any:
        if self._cas_client is None:
            self._cas_client = self._build_cas_client()
        return self._cas_client

    def _build_alb_client(self) -> Any:
        access_key_id = self.settings.get("access_key_id")
        access_key_secret = self.settings.get("access_key_secret")
        if not access_key_id or not access_key_secret:
            raise DeployError("aliyun_alb deployer requires access_key_id and access_key_secret")
        try:
            from alibabacloud_alb20200616.client import Client as AlbClient
            from alibabacloud_tea_openapi import models as open_api_models
        except ImportError as exc:
            raise DeployError("Alibaba Cloud ALB SDK is not installed. Install leet-ssl-cert[aliyun].") from exc
        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            region_id=self._region_id(),
        )
        endpoint = self.settings.get("alb_endpoint")
        if endpoint:
            config.endpoint = endpoint
        return AlbClient(config)

    def _build_cas_client(self) -> Any:
        access_key_id = self.settings.get("access_key_id")
        access_key_secret = self.settings.get("access_key_secret")
        if not access_key_id or not access_key_secret:
            raise DeployError("aliyun_alb deployer requires access_key_id and access_key_secret")
        try:
            from alibabacloud_cas20200407.client import Client as CasClient
            from alibabacloud_tea_openapi import models as open_api_models
        except ImportError as exc:
            raise DeployError("Alibaba Cloud CAS SDK is not installed. Install leet-ssl-cert[aliyun].") from exc
        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            region_id=self._region_id(),
        )
        endpoint = self.settings.get("cas_endpoint")
        if endpoint:
            config.endpoint = endpoint
        return CasClient(config)

    def _region_id(self) -> str:
        region_id = str(self.settings.get("region") or os.getenv("ALICLOUD_REGION") or "").strip()
        if not region_id:
            raise DeployError("aliyun_alb deployer requires region or ALICLOUD_REGION")
        return region_id

    def _alb_request(self, name: str) -> Any:
        try:
            from alibabacloud_alb20200616 import models as alb_models
        except ImportError as exc:
            raise DeployError("Alibaba Cloud ALB SDK is not installed. Install leet-ssl-cert[aliyun].") from exc
        return getattr(alb_models, name)

    def _cas_request(self, name: str) -> Any:
        try:
            from alibabacloud_cas20200407 import models as cas_models
        except ImportError as exc:
            raise DeployError("Alibaba Cloud CAS SDK is not installed. Install leet-ssl-cert[aliyun].") from exc
        return getattr(cas_models, name)
