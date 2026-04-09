from __future__ import annotations

from pathlib import Path

import yaml

from leet_ssl_cert.bootstrap import build_init_config, write_init_config


def test_build_init_config_includes_provider_placeholders() -> None:
    document = build_init_config(
        email="admin@example.com",
        certificate_name="site",
        domains=["example.com", "www.example.com"],
        dns_provider="cloudflare",
        deployer="aws_acm",
        deploy_settings={"region": "us-east-1"},
    )

    assert document["providers"]["cloudflare"]["api_token"] == "${CLOUDFLARE_API_TOKEN}"
    assert document["providers"]["aws"] == {}
    assert document["certificates"][0]["deploy"][0]["provider"] == "aws_acm"


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
