from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from leet_ssl_cert.bootstrap import (
    build_init_config,
    preflight_provider_environment,
    print_provider_environment_snapshot,
    write_init_config,
)
from leet_ssl_cert.errors import ConfigError


def test_build_init_config_includes_provider_placeholders() -> None:
    document = build_init_config(
        email="admin@example.com",
        certificate_name="site",
        domains=["example.com", "www.example.com"],
        dns_provider="aliyun",
        deployer="aws_acm",
        deploy_settings={"region": "us-east-1"},
    )

    assert document["providers"]["aliyun"]["access_key_id"] == "${ALICLOUD_ACCESS_KEY_ID}"
    assert document["providers"]["aws"] == {}
    assert document["certificates"][0]["deploy"][0]["provider"] == "aws_acm"


def test_build_init_config_includes_gcp_project_placeholder() -> None:
    document = build_init_config(
        email="admin@example.com",
        certificate_name="site",
        domains=["example.com"],
        dns_provider="gcp",
        deployer="gcp_lb",
        deploy_settings={"project": "my-gcp-project", "scope": "global", "target_https_proxy": "edge-proxy"},
    )

    assert document["providers"]["gcp"]["project"] == "${GCP_PROJECT}"
    assert document["certificates"][0]["deploy"][0]["provider"] == "gcp_lb"


def test_build_init_config_includes_godaddy_placeholders() -> None:
    document = build_init_config(
        email="admin@example.com",
        certificate_name="site",
        domains=["example.com"],
        dns_provider="godaddy",
        deployer="gcp_lb",
        deploy_settings={"project": "my-gcp-project", "scope": "global", "target_https_proxy": "edge-proxy"},
    )

    assert document["providers"]["godaddy"]["api_key"] == "${GODADDY_API_KEY}"
    assert document["providers"]["godaddy"]["api_secret"] == "${GODADDY_API_SECRET}"
    assert document["providers"]["gcp"]["project"] == "${GCP_PROJECT}"


def test_write_init_config_writes_yaml(tmp_path: Path) -> None:
    output = tmp_path / "leet-ssl-cert.yaml"
    path = write_init_config(
        {
            "account": {"email": "admin@example.com"},
            "certificates": [{"name": "site"}],
        },
        output,
    )

    written = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert written["account"]["email"] == "admin@example.com"


def test_preflight_provider_environment_reports_missing_env_vars(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("ALICLOUD_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("ALICLOUD_ACCESS_KEY_SECRET", raising=False)

    with pytest.raises(ConfigError, match="Missing required environment variables"):
        preflight_provider_environment(dns_provider="aliyun", deployer="aliyun_clb")

    captured = capsys.readouterr()
    assert "ALICLOUD_ACCESS_KEY_ID" in captured.err
    assert "Alibaba Cloud access key ID used to authenticate API requests." in captured.err
    assert "value: <not set>" in captured.err


def test_preflight_provider_environment_redacts_sensitive_env_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ALICLOUD_ACCESS_KEY_ID", "abc123456def")
    monkeypatch.setenv("ALICLOUD_ACCESS_KEY_SECRET", "sec123456ret")

    preflight_provider_environment(dns_provider="aliyun", deployer="aliyun_clb")

    captured = capsys.readouterr()
    assert "value: abcxxxxxxdef" in captured.err
    assert "value: secxxxxxxret" in captured.err
    assert "abc123456def" not in captured.err
    assert "sec123456ret" not in captured.err


def test_print_provider_environment_snapshot_is_scoped(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("AWS_PROFILE", "dev")
    monkeypatch.delenv("ALICLOUD_ACCESS_KEY_ID", raising=False)

    print_provider_environment_snapshot("aws")

    captured = capsys.readouterr()
    assert "AWS_PROFILE" in captured.err
    assert "value: dev" in captured.err
    assert "ALICLOUD_ACCESS_KEY_ID" not in captured.err


def test_preflight_provider_environment_reports_missing_godaddy_env_vars(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("GODADDY_API_KEY", raising=False)
    monkeypatch.delenv("GODADDY_API_SECRET", raising=False)
    monkeypatch.setenv("GCP_PROJECT", "my-gcp-project")

    with pytest.raises(ConfigError, match="Missing required environment variables"):
        preflight_provider_environment(dns_provider="godaddy", deployer="gcp_lb")

    captured = capsys.readouterr()
    assert "GODADDY_API_KEY" in captured.err
    assert "GODADDY_API_SECRET" in captured.err
