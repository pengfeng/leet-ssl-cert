"""Click CLI entry point."""

from __future__ import annotations

from pathlib import Path

import click

from .bootstrap import DEPLOYER_CHOICES, DNS_PROVIDER_CHOICES, initialize_config
from .config import load_config
from .errors import LeetSSLCertError
from .scheduler import build_cron_entry
from .service import CertificateService


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
    email = email or click.prompt("ACME account email")
    certificate_name = certificate_name or click.prompt("Certificate name")
    domains = domains or click.prompt("Domains (comma separated)")
    dns_provider = dns_provider or click.prompt("DNS provider", type=click.Choice(DNS_PROVIDER_CHOICES))
    deployer = deployer or click.prompt("Deployment provider", type=click.Choice(DEPLOYER_CHOICES))
    deploy_settings = _collect_deploy_settings(
        deployer=deployer,
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
    region: str | None,
    load_balancer_id: str | None,
    listener_id: str | None,
    listener_port: int | None,
    listener_arn: str | None,
    load_balancer_name: str | None,
) -> dict[str, object]:
    settings: dict[str, object] = {}
    if deployer in {"aliyun_clb", "aliyun_alb", "aws_acm", "aws_elb"}:
        region = region or click.prompt("Region")
        settings["region"] = region
    if deployer == "aliyun_clb":
        settings["load_balancer_id"] = load_balancer_id or click.prompt("CLB load balancer id")
        settings["listener_port"] = listener_port or click.prompt("HTTPS listener port", type=int, default=443)
    elif deployer == "aliyun_alb":
        settings["listener_id"] = listener_id or click.prompt("ALB listener id")
    elif deployer == "aws_acm":
        pass
    elif deployer == "aws_elb":
        if not listener_arn and not load_balancer_name:
            mode = click.prompt(
                "Target mode",
                type=click.Choice(("listener_arn", "classic_load_balancer")),
                default="listener_arn",
            )
            if mode == "listener_arn":
                listener_arn = click.prompt("ELBv2 listener ARN")
            else:
                load_balancer_name = click.prompt("Classic ELB name")
        if listener_arn:
            settings["listener_arn"] = listener_arn
        if load_balancer_name:
            settings["load_balancer_name"] = load_balancer_name
            settings["listener_port"] = listener_port or click.prompt("HTTPS listener port", type=int, default=443)
    return settings


if __name__ == "__main__":
    main()
