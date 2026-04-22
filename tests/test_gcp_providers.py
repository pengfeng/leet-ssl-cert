from __future__ import annotations

from types import SimpleNamespace

import pytest

from leet_ssl_cert.errors import DeployError, DNSError
from leet_ssl_cert.providers.gcp.dns import GCPCloudDNSProvider
from leet_ssl_cert.providers.gcp.lb import GCPLoadBalancerDeployer


class FakeRecordSet:
    def __init__(self, name: str, record_type: str, ttl: int, rrdatas: list[str]) -> None:
        self.name = name
        self.record_type = record_type
        self.ttl = ttl
        self.rrdatas = list(rrdatas)


class FakeChanges:
    def __init__(self) -> None:
        self.additions: list[FakeRecordSet] = []
        self.deletions: list[FakeRecordSet] = []
        self.created = False

    def add_record_set(self, record_set: FakeRecordSet) -> None:
        self.additions.append(record_set)

    def delete_record_set(self, record_set: FakeRecordSet) -> None:
        self.deletions.append(record_set)

    def create(self, client=None) -> None:
        self.created = True


class FakeManagedZone:
    def __init__(self, dns_name: str, records: list[FakeRecordSet]) -> None:
        self.dns_name = dns_name
        self._records = records
        self.last_changes: FakeChanges | None = None

    def list_resource_record_sets(self):
        return list(self._records)

    def changes(self) -> FakeChanges:
        self.last_changes = FakeChanges()
        return self.last_changes

    def resource_record_set(self, name: str, record_type: str, ttl: int, rrdatas: list[str]) -> FakeRecordSet:
        return FakeRecordSet(name, record_type, ttl, rrdatas)


def test_gcp_dns_provider_uses_project_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "env-project")
    provider = GCPCloudDNSProvider({})

    assert provider._project() == "env-project"


def test_gcp_dns_provider_create_merges_txt_values() -> None:
    existing = FakeRecordSet("_acme-challenge.example.com.", "TXT", 60, ["existing-token"])
    zone = FakeManagedZone("example.com.", [existing])
    provider = GCPCloudDNSProvider({"project": "my-gcp-project"})
    provider._client = SimpleNamespace(list_zones=lambda max_results=None: [zone])

    provider.create_txt_record("example.com", "_acme-challenge.example.com", "new-token")

    assert zone.last_changes is not None
    assert zone.last_changes.deletions[0] is existing
    assert zone.last_changes.additions[0].rrdatas == ["existing-token", "new-token"]


def test_gcp_dns_provider_delete_removes_matching_value_only() -> None:
    existing = FakeRecordSet("_acme-challenge.example.com.", "TXT", 60, ['"keep me"', "remove-me"])
    zone = FakeManagedZone("example.com.", [existing])
    provider = GCPCloudDNSProvider({"project": "my-gcp-project"})
    provider._client = SimpleNamespace(list_zones=lambda max_results=None: [zone])

    provider.delete_txt_record("example.com", "_acme-challenge.example.com", "remove-me")

    assert zone.last_changes is not None
    assert zone.last_changes.deletions[0] is existing
    assert zone.last_changes.additions[0].rrdatas == ['"keep me"']


def test_gcp_lb_binds_global_target_https_proxy() -> None:
    calls: list[tuple[str, object]] = []

    class FakeTargetHttpsProxyClient:
        def get(self, **kwargs):
            calls.append(("get", kwargs))
            return SimpleNamespace(
                ssl_certificates=[
                    "https://www.googleapis.com/compute/v1/projects/my-gcp-project/global/sslCertificates/old-cert"
                ]
            )

        def set_ssl_certificates(self, **kwargs):
            calls.append(("set", kwargs))
            return SimpleNamespace(result=lambda timeout=None: None, error_code=None)

    deployer = GCPLoadBalancerDeployer(
        {
            "project": "my-gcp-project",
            "scope": "global",
            "target_https_proxy": "edge-proxy",
        }
    )
    deployer._compute_client = lambda name: FakeTargetHttpsProxyClient() if name == "TargetHttpsProxiesClient" else None

    result = deployer.bind_certificate("cert-1")

    assert result.bound_to == "targetHttpsProxy/edge-proxy"
    assert result.old_certificate_id == "old-cert"
    assert calls[1][1]["target_https_proxies_set_ssl_certificates_request_resource"]["ssl_certificates"] == [
        "https://www.googleapis.com/compute/v1/projects/my-gcp-project/global/sslCertificates/cert-1"
    ]


def test_gcp_lb_upload_uses_regional_certificates_client() -> None:
    calls: list[tuple[str, object]] = []

    class FakeRegionalCertificatesClient:
        def insert(self, **kwargs):
            calls.append(("insert", kwargs))
            return SimpleNamespace(result=lambda timeout=None: None, error_code=None)

    deployer = GCPLoadBalancerDeployer(
        {
            "project": "my-gcp-project",
            "scope": "regional",
            "region": "us-central1",
            "target_https_proxy": "regional-proxy",
        }
    )
    deployer._compute_client = lambda name: FakeRegionalCertificatesClient() if name == "RegionSslCertificatesClient" else None

    certificate_id = deployer.upload_certificate("Site_Prod", "CERT", "KEY")

    assert certificate_id.startswith("leet-site-prod-")
    assert calls[0][1]["region"] == "us-central1"
    assert calls[0][1]["ssl_certificate_resource"]["name"] == certificate_id


def test_gcp_lb_rejects_regional_target_ssl_proxy() -> None:
    deployer = GCPLoadBalancerDeployer(
        {
            "project": "my-gcp-project",
            "scope": "regional",
            "region": "us-central1",
            "target_ssl_proxy": "ssl-proxy",
        }
    )

    with pytest.raises(DeployError, match="regional target_ssl_proxy"):
        deployer.validate_credentials()


def test_gcp_dns_provider_requires_project() -> None:
    provider = GCPCloudDNSProvider({})

    with pytest.raises(DNSError, match="requires project"):
        provider._project()
