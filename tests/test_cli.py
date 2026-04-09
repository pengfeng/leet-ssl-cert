from __future__ import annotations

from click.testing import CliRunner

from leet_ssl_cert import cli
from leet_ssl_cert.models import InitResult
from leet_ssl_cert.models import CertificateStatus


class FakeService:
    def check(self, *, name: str | None = None) -> list[CertificateStatus]:
        return [
            CertificateStatus(
                name=name or "site",
                domains=["example.com"],
                exists_locally=True,
                expires_at=None,
                remaining_days=42,
                due_for_renewal=False,
                deploy_targets=["aliyun_clb"],
                last_deploy={"aliyun_clb": {"certificate_id": "cert-site"}},
            )
        ]

    def revoke(self, *, name: str):
        return type("Result", (), {"revoked": True, "name": name})()


def test_check_command_renders_status(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_service", lambda config_path: FakeService())
    runner = CliRunner()

    result = runner.invoke(cli.main, ["check"])

    assert result.exit_code == 0
    assert "remaining_days=42" in result.output


def test_revoke_command_renders_status(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_service", lambda config_path: FakeService())
    runner = CliRunner()

    result = runner.invoke(cli.main, ["revoke", "--name", "site"])

    assert result.exit_code == 0
    assert "site: revoked" in result.output


def test_init_command_writes_config(monkeypatch, tmp_path) -> None:
    output_path = tmp_path / "leet-ssl-cert.yaml"
    monkeypatch.setattr(
        cli,
        "initialize_config",
        lambda **kwargs: InitResult(
            output_path=output_path,
            validated=False,
            dns_provider="cloudflare",
            deployer="aws_acm",
        ),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.main,
        [
            "init",
            "--output",
            str(output_path),
            "--skip-validation",
            "--email",
            "admin@example.com",
            "--name",
            "site",
            "--domains",
            "example.com,www.example.com",
            "--dns-provider",
            "cloudflare",
            "--deployer",
            "aws_acm",
            "--region",
            "us-east-1",
        ],
    )

    assert result.exit_code == 0
    assert f"Wrote config to {output_path}" in result.output
