"""Click CLI entry point."""

from __future__ import annotations

from pathlib import Path

import click

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


if __name__ == "__main__":
    main()
