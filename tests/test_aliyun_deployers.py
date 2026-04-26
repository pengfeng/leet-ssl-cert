from __future__ import annotations

from types import SimpleNamespace

import pytest

from leet_ssl_cert.errors import DeployError
from leet_ssl_cert.models import DeployResult
from leet_ssl_cert.providers.aliyun.clb import (AliyunCLBDeployer,
                                                _leaf_certificate_pem)


def test_aliyun_clb_client_config_includes_region(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeConfig:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    class FakeClient:
        def __init__(self, config) -> None:
            captured["client_config"] = config

    def fake_import_request(self, name: str):
        return object

    monkeypatch.setattr(AliyunCLBDeployer, "_import_request", fake_import_request)
    monkeypatch.setitem(
        __import__("sys").modules,
        "alibabacloud_slb20140515.client",
        SimpleNamespace(Client=FakeClient),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "alibabacloud_tea_openapi",
        SimpleNamespace(models=SimpleNamespace(Config=FakeConfig)),
    )

    deployer = AliyunCLBDeployer(
        {
            "access_key_id": "ak",
            "access_key_secret": "sk",
            "region": "cn-shanghai",
        }
    )

    deployer._build_client()

    assert captured["region_id"] == "cn-shanghai"


def test_aliyun_clb_requires_region(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALIBABA_CLOUD_REGION_ID", raising=False)
    deployer = AliyunCLBDeployer({"access_key_id": "ak", "access_key_secret": "sk"})

    with pytest.raises(DeployError, match="region"):
        deployer._region_id()


def test_aliyun_clb_validate_request_includes_region(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeRequest:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    class FakeClient:
        def describe_server_certificates(self, request) -> None:
            captured["request"] = request

    monkeypatch.setattr(AliyunCLBDeployer, "_import_request", lambda self, name: FakeRequest)
    deployer = AliyunCLBDeployer(
        {
            "access_key_id": "ak",
            "access_key_secret": "sk",
            "region": "cn-shanghai",
        }
    )
    deployer._client = FakeClient()

    deployer.validate_credentials()

    assert captured["region_id"] == "cn-shanghai"


def test_aliyun_clb_uses_leaf_certificate_from_fullchain() -> None:
    fullchain = """-----BEGIN CERTIFICATE-----
leaf
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
intermediate
-----END CERTIFICATE-----
"""

    leaf = _leaf_certificate_pem(fullchain)

    assert leaf.count("-----BEGIN CERTIFICATE-----") == 1
    assert "leaf" in leaf
    assert "intermediate" not in leaf


def test_aliyun_clb_bind_uses_generated_httpslistener_method(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeBody:
        server_certificate_id = "old-cert"

    class FakeClient:
        def describe_load_balancer_httpslistener_attribute(self, request):
            calls.append("describe")
            return SimpleNamespace(body=FakeBody())

        def set_load_balancer_httpslistener_attribute(self, request):
            calls.append("set")

    class FakeRequest:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(AliyunCLBDeployer, "_import_request", lambda self, name: FakeRequest)
    deployer = AliyunCLBDeployer(
        {
            "access_key_id": "ak",
            "access_key_secret": "sk",
            "region": "cn-shanghai",
            "load_balancer_id": "lb-test",
            "listener_port": 443,
        }
    )
    deployer._client = FakeClient()

    result = deployer.bind_certificate("new-cert")

    assert isinstance(result, DeployResult)
    assert result.old_certificate_id == "old-cert"
    assert calls == ["describe", "set"]
