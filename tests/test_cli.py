from __future__ import annotations

import json

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
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli,
        "initialize_config",
        lambda **kwargs: InitResult(
            output_path=output_path,
            validated=False,
            dns_provider="aliyun",
            deployer="aliyun_clb",
        ),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.main,
        [
            "init",
            "aliyun",
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
            "aliyun",
            "--deployer",
            "aliyun_clb",
            "--region",
            "cn-hangzhou",
            "--load-balancer-id",
            "lb-123",
            "--listener-port",
            "443",
        ],
    )

    assert result.exit_code == 0
    assert f"Wrote config to {output_path}" in result.output
    saved_inputs = json.loads(
        (tmp_path / ".leet" / ".init-inputs.json").read_text(encoding="utf-8")
    )
    assert saved_inputs["email"] == "admin@example.com"
    assert saved_inputs["region"] == "cn-hangzhou"


def test_init_prompts_to_overwrite_existing_config(monkeypatch, tmp_path) -> None:
    output_path = tmp_path / "leet-ssl-cert.yaml"
    output_path.write_text("existing", encoding="utf-8")
    captured_kwargs = {}

    def fake_initialize_config(**kwargs):
        captured_kwargs.update(kwargs)
        return InitResult(
            output_path=kwargs["output_path"],
            validated=False,
            dns_provider=kwargs["dns_provider"],
            deployer=kwargs["deployer"],
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "initialize_config", fake_initialize_config)
    runner = CliRunner()

    result = runner.invoke(
        cli.main,
        [
            "init",
            "aliyun",
            "--output",
            str(output_path),
            "--skip-validation",
            "--email",
            "admin@example.com",
            "--name",
            "site",
            "--domains",
            "example.com",
            "--dns-provider",
            "aliyun",
            "--deployer",
            "aliyun_clb",
            "--region",
            "cn-hangzhou",
            "--load-balancer-id",
            "lb-123",
            "--listener-port",
            "443",
        ],
        input="overwrite\n",
    )

    assert result.exit_code == 0
    assert captured_kwargs["output_path"] == output_path
    assert captured_kwargs["force"] is True


def test_init_allows_aborting_when_output_exists(monkeypatch, tmp_path) -> None:
    output_path = tmp_path / "leet-ssl-cert.yaml"
    output_path.write_text("existing", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        cli.main,
        [
            "init",
            "aliyun",
            "--output",
            str(output_path),
            "--skip-validation",
            "--email",
            "admin@example.com",
            "--name",
            "site",
            "--domains",
            "example.com",
            "--dns-provider",
            "aliyun",
            "--deployer",
            "aliyun_clb",
            "--region",
            "cn-hangzhou",
            "--load-balancer-id",
            "lb-123",
            "--listener-port",
            "443",
        ],
        input="abort\n",
    )

    assert result.exit_code != 0
    assert "Aborted!" in result.output


def test_init_prompts_for_different_output_path(monkeypatch, tmp_path) -> None:
    output_path = tmp_path / "leet-ssl-cert.yaml"
    output_path.write_text("existing", encoding="utf-8")
    new_output_path = tmp_path / "leet-ssl-cert-dev.yaml"
    captured_kwargs = {}

    def fake_initialize_config(**kwargs):
        captured_kwargs.update(kwargs)
        return InitResult(
            output_path=kwargs["output_path"],
            validated=False,
            dns_provider=kwargs["dns_provider"],
            deployer=kwargs["deployer"],
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "initialize_config", fake_initialize_config)
    runner = CliRunner()

    result = runner.invoke(
        cli.main,
        [
            "init",
            "aliyun",
            "--output",
            str(output_path),
            "--skip-validation",
            "--email",
            "admin@example.com",
            "--name",
            "site",
            "--domains",
            "example.com",
            "--dns-provider",
            "aliyun",
            "--deployer",
            "aliyun_clb",
            "--region",
            "cn-hangzhou",
            "--load-balancer-id",
            "lb-123",
            "--listener-port",
            "443",
        ],
        input=f"different_file\n{new_output_path}\n",
    )

    assert result.exit_code == 0
    assert captured_kwargs["output_path"] == new_output_path
    assert captured_kwargs["force"] is False


def test_init_command_prefills_prompts_from_cache(monkeypatch, tmp_path) -> None:
    output_path = tmp_path / "leet-ssl-cert.yaml"
    cache_dir = tmp_path / ".leet"
    cache_dir.mkdir()
    (cache_dir / ".init-inputs.json").write_text(
        json.dumps(
            {
                "dns_provider": "aliyun",
                "deployer": "aws_acm",
                "email": "admin@example.com",
                "certificate_name": "site",
                "domains": "example.com,www.example.com",
                "region": "us-west-2",
            }
        ),
        encoding="utf-8",
    )
    captured_kwargs = {}

    def fake_initialize_config(**kwargs):
        captured_kwargs.update(kwargs)
        return InitResult(
            output_path=output_path,
            validated=False,
            dns_provider=kwargs["dns_provider"],
            deployer=kwargs["deployer"],
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "initialize_config", fake_initialize_config)
    runner = CliRunner()

    result = runner.invoke(
        cli.main,
        [
            "init",
            "aws",
            "--output",
            str(output_path),
            "--skip-validation",
            "--concise",
        ],
        input="\n\n\n\n\n\n",
    )

    assert result.exit_code == 0
    assert captured_kwargs["dns_provider"] == "aliyun"
    assert captured_kwargs["deployer"] == "aws_acm"
    assert captured_kwargs["email"] == "admin@example.com"
    assert captured_kwargs["certificate_name"] == "site"
    assert captured_kwargs["domains"] == ["example.com", "www.example.com"]
    assert captured_kwargs["deploy_settings"] == {"region": "us-west-2"}


def test_prompt_region_accepts_custom(monkeypatch) -> None:
    answers = iter(["custom", "me-central-1"])
    monkeypatch.setattr(cli.click, "prompt", lambda *args, **kwargs: next(answers))

    region = cli._prompt_region("aws", concise=True)

    assert region == "me-central-1"


def test_init_fails_on_env_preflight_after_dns_provider_prompt(
    monkeypatch, tmp_path
) -> None:
    events: list[str] = []

    def fake_prompt(text, **kwargs):
        events.append(f"prompt:{text}")
        if text == "DNS provider":
            return "aliyun"
        raise AssertionError(f"unexpected prompt: {text}")

    monkeypatch.setattr(cli.click, "prompt", fake_prompt)
    monkeypatch.chdir(tmp_path)

    def fake_preflight(**kwargs):
        events.append(
            f"preflight:{kwargs['dns_provider']}->{kwargs['deployment_provider']}"
        )
        raise ConfigError(
            "Missing required environment variables. Set the variables listed above and retry."
        )

    monkeypatch.setattr(cli, "preflight_provider_namespaces", fake_preflight)
    runner = CliRunner()

    result = runner.invoke(cli.main, ["init", "aliyun"])

    assert result.exit_code != 0
    assert "Error: Missing required environment variables." in result.output
    assert events == ["prompt:DNS provider", "preflight:aliyun->aliyun"]


def test_init_filters_deployer_prompt_to_selected_cloud_provider(
    monkeypatch, tmp_path
) -> None:
    events: list[str] = []

    def fake_prompt(text, **kwargs):
        events.append(f"prompt:{text}")
        if text == "DNS provider":
            return "aliyun"
        if text == "Deployment provider":
            assert tuple(kwargs["type"].choices) == ("aws_acm", "aws_elb")
            return "aws_acm"
        raise AssertionError(f"unexpected prompt: {text}")

    monkeypatch.setattr(cli.click, "prompt", fake_prompt)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli,
        "preflight_provider_namespaces",
        lambda **kwargs: events.append(
            f"preflight:{kwargs['dns_provider']}->{kwargs['deployment_provider']}"
        ),
    )
    monkeypatch.setattr(
        cli,
        "initialize_config",
        lambda **kwargs: InitResult(
            output_path=kwargs["output_path"],
            validated=False,
            dns_provider=kwargs["dns_provider"],
            deployer=kwargs["deployer"],
        ),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.main,
        [
            "init",
            "aws",
            "--skip-validation",
            "--email",
            "admin@example.com",
            "--name",
            "site",
            "--domains",
            "example.com",
            "--region",
            "us-east-1",
        ],
    )

    assert result.exit_code == 0
    assert events == ["prompt:DNS provider", "prompt:Deployment provider"]


def test_init_rejects_deployer_outside_selected_cloud_provider(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "preflight_provider_namespaces", lambda **kwargs: None)
    runner = CliRunner()

    result = runner.invoke(
        cli.main,
        [
            "init",
            "aliyun",
            "--dns-provider",
            "aliyun",
            "--deployer",
            "aws_acm",
        ],
    )

    assert result.exit_code != 0
    assert (
        "Deployment provider 'aws_acm' is not supported for cloud provider 'aliyun'."
        in result.output
    )


def test_init_requires_provider() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.main, ["init"])

    assert result.exit_code != 0
    assert "Missing argument 'PROVIDER'" in result.output


def test_init_gcp_command_writes_config(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "leet-ssl-cert.yaml"
    captured_kwargs = {}

    def fake_initialize_config(**kwargs):
        captured_kwargs.update(kwargs)
        return InitResult(
            output_path=kwargs["output_path"],
            validated=False,
            dns_provider=kwargs["dns_provider"],
            deployer=kwargs["deployer"],
        )

    monkeypatch.setattr(cli, "initialize_config", fake_initialize_config)
    runner = CliRunner()

    result = runner.invoke(
        cli.main,
        [
            "init",
            "gcp",
            "--output",
            str(output_path),
            "--skip-validation",
            "--email",
            "admin@example.com",
            "--name",
            "site",
            "--domains",
            "example.com",
            "--dns-provider",
            "gcp",
            "--deployer",
            "gcp_lb",
            "--project",
            "my-gcp-project",
            "--scope",
            "global",
            "--target-https-proxy",
            "edge-proxy",
        ],
    )

    assert result.exit_code == 0
    assert captured_kwargs["dns_provider"] == "gcp"
    assert captured_kwargs["deployer"] == "gcp_lb"
    assert captured_kwargs["deploy_settings"] == {
        "project": "my-gcp-project",
        "scope": "global",
        "target_https_proxy": "edge-proxy",
    }


def test_init_gcp_command_accepts_godaddy_dns_provider(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "leet-ssl-cert.yaml"
    captured_kwargs = {}

    def fake_initialize_config(**kwargs):
        captured_kwargs.update(kwargs)
        return InitResult(
            output_path=kwargs["output_path"],
            validated=False,
            dns_provider=kwargs["dns_provider"],
            deployer=kwargs["deployer"],
        )

    monkeypatch.setattr(cli, "initialize_config", fake_initialize_config)
    runner = CliRunner()

    result = runner.invoke(
        cli.main,
        [
            "init",
            "gcp",
            "--output",
            str(output_path),
            "--skip-validation",
            "--email",
            "admin@example.com",
            "--name",
            "site",
            "--domains",
            "example.com",
            "--dns-provider",
            "godaddy",
            "--deployer",
            "gcp_lb",
            "--project",
            "my-gcp-project",
            "--scope",
            "global",
            "--target-https-proxy",
            "edge-proxy",
        ],
    )

    assert result.exit_code == 0
    assert captured_kwargs["dns_provider"] == "godaddy"
    assert captured_kwargs["deployer"] == "gcp_lb"
