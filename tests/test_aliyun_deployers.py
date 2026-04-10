from __future__ import annotations

from types import SimpleNamespace

import pytest

from leet_ssl_cert.deployer.aliyun_clb import AliyunCLBDeployer, _leaf_certificate_pem
from leet_ssl_cert.errors import DeployError


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
    monkeypatch.delenv("ALICLOUD_REGION", raising=False)
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
