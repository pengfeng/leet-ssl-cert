from __future__ import annotations

from click.testing import CliRunner

from leet_ssl_cert import cli
from leet_ssl_cert.errors import ConfigError
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


def test_prompt_region_accepts_custom(monkeypatch) -> None:
    answers = iter(["custom", "me-central-1"])
    monkeypatch.setattr(cli.click, "prompt", lambda *args, **kwargs: next(answers))

    region = cli._prompt_region("aws", concise=True)

    assert region == "me-central-1"


def test_init_fails_early_on_env_preflight(monkeypatch) -> None:
    prompts: list[str] = []

    def fake_prompt(text, **kwargs):
        prompts.append(text)
        if text == "DNS provider":
            return "aliyun"
        if text == "Deployment provider":
            return "aliyun_clb"
        raise AssertionError(f"unexpected prompt: {text}")

    monkeypatch.setattr(cli.click, "prompt", fake_prompt)
    monkeypatch.setattr(
        cli,
        "preflight_provider_environment",
        lambda **kwargs: (_ for _ in ()).throw(ConfigError("Missing required environment variables. Set the variables listed above and retry.")),
    )
    runner = CliRunner()

    result = runner.invoke(cli.main, ["init"])

    assert result.exit_code != 0
    assert "Error: Missing required environment variables." in result.output
    assert prompts == ["DNS provider", "Deployment provider"]
