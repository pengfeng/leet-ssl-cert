"""AWS ELB / ALB deployer."""

from __future__ import annotations

from typing import Any

from leet_ssl_cert.errors import DeployError
from leet_ssl_cert.models import DeployResult
from leet_ssl_cert.providers.aws.acm import AWSACMDeployer


class AWSELBDeployer(AWSACMDeployer):
    """Import certificates into ACM and bind them to an AWS load balancer listener."""

    def bind_certificate(self, certificate_id: str) -> DeployResult:
        region = self._required("region")
        listener_arn = str(self.settings.get("listener_arn", "")).strip()
        load_balancer_name = str(self.settings.get("load_balancer_name", "")).strip()

        if listener_arn:
            client = self._elbv2_client(region)
            old_certificate_id = self._get_listener_default_certificate(
                client, listener_arn
            )
            client.modify_listener(
                ListenerArn=listener_arn,
                Certificates=[{"CertificateArn": certificate_id}],
            )
            return DeployResult(
                certificate_id=certificate_id,
                provider="aws_elb",
                bound_to=listener_arn,
                old_certificate_id=old_certificate_id,
            )

        if load_balancer_name:
            listener_port = int(self.settings.get("listener_port", 443))
            client = self._classic_elb_client(region)
            old_certificate_id = None
            client.set_load_balancer_listener_ssl_certificate(
                LoadBalancerName=load_balancer_name,
                LoadBalancerPort=listener_port,
                SSLCertificateId=certificate_id,
            )
            return DeployResult(
                certificate_id=certificate_id,
                provider="aws_elb",
                bound_to=f"{load_balancer_name}:{listener_port}",
                old_certificate_id=old_certificate_id,
            )

        raise DeployError(
            "aws_elb deployer requires either listener_arn or load_balancer_name"
        )

    def validate_credentials(self) -> None:
        region = self._required("region")
        listener_arn = str(self.settings.get("listener_arn", "")).strip()
        load_balancer_name = str(self.settings.get("load_balancer_name", "")).strip()
        super().validate_credentials()
        if listener_arn:
            self._elbv2_client(region).describe_listeners(ListenerArns=[listener_arn])
            return
        if load_balancer_name:
            self._classic_elb_client(region).describe_load_balancers(
                LoadBalancerNames=[load_balancer_name]
            )
            return
        raise DeployError(
            "aws_elb deployer requires either listener_arn or load_balancer_name"
        )

    def cleanup_old_certificates(self, name: str, keep: int = 1) -> list[str]:
        deleted = super().cleanup_old_certificates(name, keep)
        listener_arn = str(self.settings.get("listener_arn", "")).strip()
        if listener_arn:
            client = self._elbv2_client(self._required("region"))
            for certificate_arn in deleted:
                try:
                    client.remove_listener_certificates(
                        ListenerArn=listener_arn,
                        Certificates=[{"CertificateArn": certificate_arn}],
                    )
                except Exception:
                    pass
        return deleted

    def _get_listener_default_certificate(
        self, client: Any, listener_arn: str
    ) -> str | None:
        response = client.describe_listeners(ListenerArns=[listener_arn])
        listeners = response.get("Listeners", [])
        if not listeners:
            return None
        certificates = listeners[0].get("Certificates", [])
        if not certificates:
            return None
        return certificates[0].get("CertificateArn")

    def _elbv2_client(self, region: str) -> Any:
        return self._session(region).client("elbv2")

    def _classic_elb_client(self, region: str) -> Any:
        return self._session(region).client("elb")

    def _session(self, region: str) -> Any:
        try:
            import boto3
        except ImportError as exc:
            raise DeployError(
                "boto3 is not installed. Install leet-ssl-cert[aws]."
            ) from exc
        return boto3.session.Session(
            aws_access_key_id=self.settings.get("access_key_id"),
            aws_secret_access_key=self.settings.get("secret_access_key"),
            aws_session_token=self.settings.get("session_token"),
            region_name=region,
            profile_name=self.settings.get("profile"),
        )
