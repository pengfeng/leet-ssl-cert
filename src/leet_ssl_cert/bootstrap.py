"""Interactive setup helpers for Phase 2 commands."""

from __future__ import annotations

from pathlib import Path
import os
from typing import Any

import yaml

from .deployer import get_deployer
from .dns import get_dns_provider
from .errors import ConfigError
from .models import InitResult

DNS_PROVIDER_CHOICES = ("aliyun", "cloudflare", "aws")
DEPLOYER_CHOICES = ("aliyun_clb", "aliyun_alb", "aws_acm", "aws_elb")


def build_init_config(
    *,
    email: str,
    certificate_name: str,
    domains: list[str],
    dns_provider: str,
    deployer: str,
    deploy_settings: dict[str, Any],
) -> dict[str, Any]:
    """Render a config document from interactive answers."""
    namespaces = {_provider_namespace(dns_provider), _provider_namespace(deployer)}
    providers = {namespace: _provider_placeholder_settings(namespace) for namespace in namespaces}
    return {
        "account": {"email": email},
        "acme": {
            "directory_url": "https://acme-v02.api.letsencrypt.org/directory",
            "key_size": 2048,
            "renewal_days": 30,
        },
        "storage": {"base_dir": "~/.leet-ssl-cert/certs"},
        "certificates": [
            {
                "name": certificate_name,
                "domains": domains,
                "dns_provider": dns_provider,
                "deploy": [{"provider": deployer, **deploy_settings}],
            }
        ],
        "providers": providers,
    }


def write_init_config(document: dict[str, Any], output_path: str | Path, *, force: bool = False) -> Path:
    """Write an init-generated config file to disk."""
    path = Path(output_path).expanduser()
    if path.exists() and not force:
        raise ConfigError(f"Config file already exists: {path}. Use --force to overwrite it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def validate_setup(
    *,
    dns_provider: str,
    deployer: str,
    deploy_settings: dict[str, Any],
) -> None:
    """Validate provider and deployer credentials using environment-backed settings."""
    dns_settings = _runtime_provider_settings(_provider_namespace(dns_provider), deploy_settings)
    get_dns_provider(dns_provider, dns_settings).validate_credentials()

    deployer_settings = _runtime_provider_settings(_provider_namespace(deployer), deploy_settings)
    deployer_settings.update(deploy_settings)
    get_deployer(deployer, deployer_settings).validate_credentials()


def initialize_config(
    *,
    email: str,
    certificate_name: str,
    domains: list[str],
    dns_provider: str,
    deployer: str,
    deploy_settings: dict[str, Any],
    output_path: str | Path,
    force: bool = False,
    validate: bool = True,
) -> InitResult:
    """Build, optionally validate, and write a config file."""
    document = build_init_config(
        email=email,
        certificate_name=certificate_name,
        domains=domains,
        dns_provider=dns_provider,
        deployer=deployer,
        deploy_settings=deploy_settings,
    )
    if validate:
        validate_setup(dns_provider=dns_provider, deployer=deployer, deploy_settings=deploy_settings)
    written_path = write_init_config(document, output_path, force=force)
    return InitResult(
        output_path=written_path,
        validated=validate,
        dns_provider=dns_provider,
        deployer=deployer,
    )


def _provider_namespace(provider_name: str) -> str:
    if "_" not in provider_name:
        return provider_name
    return provider_name.split("_", 1)[0]


def _provider_placeholder_settings(namespace: str) -> dict[str, Any]:
    if namespace == "aliyun":
        return {
            "access_key_id": "${ALICLOUD_ACCESS_KEY_ID}",
            "access_key_secret": "${ALICLOUD_ACCESS_KEY_SECRET}",
        }
    if namespace == "cloudflare":
        return {"api_token": "${CLOUDFLARE_API_TOKEN}"}
    if namespace == "aws":
        return {}
    return {}


def _runtime_provider_settings(namespace: str, deploy_settings: dict[str, Any]) -> dict[str, Any]:
    if namespace == "aliyun":
        access_key_id = os.getenv("ALICLOUD_ACCESS_KEY_ID")
        access_key_secret = os.getenv("ALICLOUD_ACCESS_KEY_SECRET")
        if not access_key_id or not access_key_secret:
            raise ConfigError("Alibaba Cloud validation requires ALICLOUD_ACCESS_KEY_ID and ALICLOUD_ACCESS_KEY_SECRET")
        return {
            "access_key_id": access_key_id,
            "access_key_secret": access_key_secret,
        }
    if namespace == "cloudflare":
        api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        if not api_token:
            raise ConfigError("Cloudflare validation requires CLOUDFLARE_API_TOKEN")
        return {"api_token": api_token}
    if namespace == "aws":
        settings: dict[str, Any] = {}
        for env_name, key in (
            ("AWS_ACCESS_KEY_ID", "access_key_id"),
            ("AWS_SECRET_ACCESS_KEY", "secret_access_key"),
            ("AWS_SESSION_TOKEN", "session_token"),
            ("AWS_PROFILE", "profile"),
        ):
            env_value = os.getenv(env_name)
            if env_value:
                settings[key] = env_value
        region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or deploy_settings.get("region")
        if region:
            settings["region"] = region
        return settings
    return {}
