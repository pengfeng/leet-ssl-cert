"""Click CLI entry point."""

from __future__ import annotations

from pathlib import Path

import click

from .bootstrap import (
    DEPLOYER_CHOICES,
    DNS_PROVIDER_CHOICES,
    initialize_config,
    preflight_provider_environment,
    print_setup_environment_snapshot,
)
from .config import load_config
from .errors import LeetSSLCertError
from .scheduler import build_cron_entry
from .service import CertificateService

POPULAR_REGIONS = {
    "aliyun": [
        ("cn-hangzhou", "Hangzhou"),
        ("cn-shanghai", "Shanghai"),
        ("cn-beijing", "Beijing"),
        ("ap-southeast-1", "Singapore"),
        ("us-west-1", "Silicon Valley"),
    ],
    "aws": [
        ("us-east-1", "N. Virginia"),
        ("us-west-2", "Oregon"),
        ("eu-west-1", "Ireland"),
        ("ap-southeast-1", "Singapore"),
        ("ap-northeast-1", "Tokyo"),
    ],
}


def build_service(config_path: str | None) -> CertificateService:
    """Construct a service instance from a config path."""
    return CertificateService(load_config(config_path))


@click.group()
@click.option("--config", "config_path", type=click.Path(dir_okay=False, path_type=Path), help="Path to config file.")
@click.pass_context
def main(ctx: click.Context, config_path: Path | None) -> None:
    """Automate ACME issuance and cloud certificate deployment."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = str(config_path) if config_path else None


@main.command()
@click.option("--name", help="Process only one certificate by logical name.")
@click.option("--force", is_flag=True, help="Force renewal even if certificate is not due.")
@click.option("--dry-run", is_flag=True, help="Report what would happen without mutating state.")
@click.pass_context
def issue(ctx: click.Context, name: str | None, force: bool, dry_run: bool) -> None:
    """Issue or renew certificates."""
    _run_command(ctx, lambda service: _render_issue(service.issue(name=name, force=force, dry_run=dry_run)))


@main.command()
@click.option("--name", help="Deploy only one certificate by logical name.")
@click.pass_context
def deploy(ctx: click.Context, name: str | None) -> None:
    """Deploy locally stored certificates."""
    _run_command(ctx, lambda service: _render_deploy(service.deploy(name=name)))


@main.command()
@click.option("--name", help="Run only one certificate by logical name.")
@click.option("--force", is_flag=True, help="Force renewal even if certificate is not due.")
@click.option("--dry-run", is_flag=True, help="Report what would happen without mutating state.")
@click.pass_context
def run(ctx: click.Context, name: str | None, force: bool, dry_run: bool) -> None:
    """Issue and then deploy certificates."""
    _run_command(ctx, lambda service: _render_run(service.run(name=name, force=force, dry_run=dry_run)))


@main.command()
@click.option("--name", help="Check only one certificate by logical name.")
@click.pass_context
def check(ctx: click.Context, name: str | None) -> None:
    """Report local certificate status."""
    _run_command(ctx, lambda service: _render_check(service.check(name=name)))


@main.command()
@click.option("--name", "certificate_name", required=True, help="Logical certificate name.")
@click.pass_context
def revoke(ctx: click.Context, certificate_name: str) -> None:
    """Revoke a stored certificate via ACME."""
    _run_command(ctx, lambda service: _render_revoke(service.revoke(name=certificate_name)))


@main.command()
@click.option("--output", "output_path", default="leet-ssl-cert.yaml", show_default=True, type=click.Path(dir_okay=False, path_type=Path), help="Where to write the generated config.")
@click.option("--force", is_flag=True, help="Overwrite an existing config file.")
@click.option("--skip-validation", is_flag=True, help="Write the config without validating provider credentials.")
@click.option("--concise", is_flag=True, help="Skip the explanatory text and ask only the necessary questions.")
@click.option("--email", help="ACME account email.")
@click.option("--name", "certificate_name", help="Logical certificate name.")
@click.option("--domains", help="Comma-separated domain list.")
@click.option("--dns-provider", type=click.Choice(DNS_PROVIDER_CHOICES), help="DNS provider for DNS-01 challenges.")
@click.option("--deployer", type=click.Choice(DEPLOYER_CHOICES), help="Deployment target provider.")
@click.option("--region", help="Cloud region for deployers that need one.")
@click.option("--load-balancer-id", help="Alibaba Cloud CLB load balancer id.")
@click.option("--listener-id", help="Alibaba Cloud ALB listener id.")
@click.option("--listener-port", type=int, help="HTTPS listener port.")
@click.option("--listener-arn", help="AWS ELBv2 listener ARN.")
@click.option("--load-balancer-name", help="AWS Classic ELB name.")
def init(
    output_path: Path,
    force: bool,
    skip_validation: bool,
    concise: bool,
    email: str | None,
    certificate_name: str | None,
    domains: str | None,
    dns_provider: str | None,
    deployer: str | None,
    region: str | None,
    load_balancer_id: str | None,
    listener_id: str | None,
    listener_port: int | None,
    listener_arn: str | None,
    load_balancer_name: str | None,
) -> None:
    """Interactively generate a config file and optionally validate credentials."""
    try:
        validated_provider_selection = False
        if not skip_validation:
            if dns_provider and deployer:
                preflight_provider_environment(dns_provider=dns_provider, deployer=deployer)
                validated_provider_selection = True
            else:
                print_setup_environment_snapshot()

        dns_provider = dns_provider or _prompt_with_help(
            "DNS provider",
            "This is the DNS service where the tool will create temporary TXT records for ACME DNS-01 verification.",
            concise=concise,
            type=click.Choice(DNS_PROVIDER_CHOICES),
        )
        deployer = deployer or _prompt_with_help(
            "Deployment provider",
            "This is the cloud target where the issued certificate will be uploaded or attached after it is created.",
            concise=concise,
            type=click.Choice(DEPLOYER_CHOICES),
        )

        if not skip_validation and not validated_provider_selection:
            preflight_provider_environment(dns_provider=dns_provider, deployer=deployer)

        email = email or _prompt_with_help(
            "ACME account email",
            "This email creates or reuses your ACME account. Certificate authorities like Let's Encrypt may use it for expiry notices or account-related messages.",
            concise=concise,
        )
        certificate_name = certificate_name or _prompt_with_help(
            "Certificate name",
            "This is a local label used for filenames, logs, and selecting one certificate with --name later.",
            concise=concise,
        )
        domains = domains or _prompt_with_help(
            "Domains (comma separated)",
            "These are the hostnames that will be included in the certificate, such as example.com and www.example.com.",
            concise=concise,
        )
        deploy_settings = _collect_deploy_settings(
            deployer=deployer,
            concise=concise,
            region=region,
            load_balancer_id=load_balancer_id,
            listener_id=listener_id,
            listener_port=listener_port,
            listener_arn=listener_arn,
            load_balancer_name=load_balancer_name,
        )
        result = initialize_config(
            email=email,
            certificate_name=certificate_name,
            domains=_parse_domains(domains),
            dns_provider=dns_provider,
            deployer=deployer,
            deploy_settings=deploy_settings,
            output_path=output_path,
            force=force,
            validate=not skip_validation,
        )
        if result.validated:
            click.echo(f"Validated credentials for {result.dns_provider} and {result.deployer}")
        click.echo(f"Wrote config to {result.output_path}")
    except LeetSSLCertError as exc:
        raise click.ClickException(str(exc)) from exc


@main.command()
@click.option("--schedule", default="0 2 * * *", show_default=True, help="Cron expression to use.")
@click.pass_context
def cron(ctx: click.Context, schedule: str) -> None:
    """Generate a cron entry for unattended renewal."""
    config_path = Path(ctx.obj["config_path"]) if ctx.obj.get("config_path") else load_config().path
    click.echo(build_cron_entry(schedule, config_path))


def _run_command(ctx: click.Context, runner: callable) -> None:
    try:
        service = build_service(ctx.obj.get("config_path"))
        runner(service)
    except LeetSSLCertError as exc:
        raise click.ClickException(str(exc)) from exc


def _render_issue(results: list) -> None:
    for result in results:
        line = f"{result.name}: {result.action}"
        if result.reason:
            line += f" ({result.reason})"
        if result.expires_at:
            line += f" expires={result.expires_at.isoformat()}"
        click.echo(line)


def _render_deploy(results: list) -> None:
    for result in results:
        line = f"{result.name}: deployed via {result.provider} certificate_id={result.certificate_id} bound_to={result.bound_to}"
        if result.deleted_certificate_ids:
            line += f" deleted={','.join(result.deleted_certificate_ids)}"
        click.echo(line)


def _render_run(results: tuple[list, list]) -> None:
    issue_results, deploy_results = results
    _render_issue(issue_results)
    if deploy_results:
        _render_deploy(deploy_results)


def _render_check(results: list) -> None:
    for result in results:
        line = f"{result.name}: "
        if result.exists_locally:
            line += f"present remaining_days={result.remaining_days} due={result.due_for_renewal}"
        else:
            line += "missing due=True"
        if result.last_deploy:
            line += f" deploys={','.join(sorted(result.last_deploy.keys()))}"
        click.echo(line)


def _render_revoke(result) -> None:
    if result.revoked:
        click.echo(f"{result.name}: revoked")


def _parse_domains(domains: str) -> list[str]:
    parsed = [domain.strip() for domain in domains.split(",") if domain.strip()]
    if not parsed:
        raise click.ClickException("At least one domain is required")
    return parsed


def _collect_deploy_settings(
    *,
    deployer: str,
    concise: bool,
    region: str | None,
    load_balancer_id: str | None,
    listener_id: str | None,
    listener_port: int | None,
    listener_arn: str | None,
    load_balancer_name: str | None,
) -> dict[str, object]:
    settings: dict[str, object] = {}
    if deployer in {"aliyun_clb", "aliyun_alb", "aws_acm", "aws_elb"}:
        namespace = deployer.split("_", 1)[0]
        region = region or _prompt_region(namespace, concise=concise)
        settings["region"] = region
    if deployer == "aliyun_clb":
        settings["load_balancer_id"] = load_balancer_id or _prompt_with_help(
            "CLB load balancer id",
            "This is the Alibaba Cloud CLB instance ID that already serves your traffic.",
            concise=concise,
        )
        settings["listener_port"] = listener_port or _prompt_with_help(
            "HTTPS listener port",
            "This is the HTTPS listener port on the CLB that should use the uploaded certificate.",
            concise=concise,
            type=int,
            default=443,
        )
    elif deployer == "aliyun_alb":
        settings["listener_id"] = listener_id or _prompt_with_help(
            "ALB listener id",
            "This is the Alibaba Cloud ALB listener ID that should be associated with the certificate.",
            concise=concise,
        )
    elif deployer == "aws_acm":
        pass
    elif deployer == "aws_elb":
        if not listener_arn and not load_balancer_name:
            mode = _prompt_with_help(
                "Target mode",
                "Choose listener_arn for Application or Network Load Balancer listeners, or classic_load_balancer for the older Classic ELB service.",
                concise=concise,
                type=click.Choice(("listener_arn", "classic_load_balancer")),
                default="listener_arn",
            )
            if mode == "listener_arn":
                listener_arn = _prompt_with_help(
                    "ELBv2 listener ARN",
                    "This is the full ARN of the AWS ALB or NLB listener that should use the certificate.",
                    concise=concise,
                )
            else:
                load_balancer_name = _prompt_with_help(
                    "Classic ELB name",
                    "This is the name of the Classic Load Balancer that should use the certificate.",
                    concise=concise,
                )
        if listener_arn:
            settings["listener_arn"] = listener_arn
        if load_balancer_name:
            settings["load_balancer_name"] = load_balancer_name
            settings["listener_port"] = listener_port or _prompt_with_help(
                "HTTPS listener port",
                "This is the Classic ELB listener port that should use the certificate.",
                concise=concise,
                type=int,
                default=443,
            )
    return settings


def _prompt_with_help(
    text: str,
    explanation: str,
    *,
    concise: bool,
    type=None,
    default=None,
):
    if not concise:
        click.echo(f"\n{text}")
        click.echo(f"  {explanation}")
    return click.prompt(text, type=type, default=default)


def _prompt_region(namespace: str, *, concise: bool) -> str:
    popular_regions = POPULAR_REGIONS.get(namespace, [])
    if not concise and popular_regions:
        click.echo("\nRegion")
        click.echo("  Choose the cloud region where your load balancer or certificate resource lives.")
        click.echo("  Popular options:")
        for code, label in popular_regions:
            click.echo(f"  - {code}: {label}")
        click.echo("  - custom: enter another region code")
    if popular_regions:
        choice = click.prompt(
            "Region",
            type=click.Choice([code for code, _ in popular_regions] + ["custom"]),
            default=popular_regions[0][0],
        )
        if choice != "custom":
            return choice
    return click.prompt("Custom region")


if __name__ == "__main__":
    main()
