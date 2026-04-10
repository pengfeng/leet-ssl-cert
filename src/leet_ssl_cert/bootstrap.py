"""Interactive setup helpers for Phase 2 commands."""

from __future__ import annotations

from pathlib import Path
import os
import sys
from typing import Any

import yaml

from leet_ssl_cert.errors import ConfigError
from leet_ssl_cert.models import InitResult
from leet_ssl_cert.providers import get_deployer, get_dns_provider

INIT_PROVIDER_CHOICES = ("aliyun", "aws", "gcp")
DNS_PROVIDER_CHOICES = ("aliyun", "aws")
DEPLOYER_CHOICES = ("aliyun_clb", "aliyun_alb", "aws_acm", "aws_elb")
ENV_VAR_DEFINITIONS = {
    "ALICLOUD_ACCESS_KEY_ID": "Alibaba Cloud access key ID used to authenticate API requests.",
    "ALICLOUD_ACCESS_KEY_SECRET": "Alibaba Cloud access key secret paired with the access key ID.",
    "AWS_ACCESS_KEY_ID": "AWS access key ID used by boto3 when using environment-based credentials.",
    "AWS_SECRET_ACCESS_KEY": "AWS secret access key paired with AWS_ACCESS_KEY_ID.",
    "AWS_SESSION_TOKEN": "Temporary AWS session token used with short-lived credentials.",
    "AWS_PROFILE": "AWS shared credential profile name for boto3.",
    "AWS_REGION": "Default AWS region used by boto3 clients.",
    "AWS_DEFAULT_REGION": "Fallback AWS region used by boto3 when AWS_REGION is unset.",
    "GOOGLE_APPLICATION_CREDENTIALS": "Path to a Google Cloud service account JSON key for Application Default Credentials.",
    "GCP_PROJECT": "Google Cloud project ID used by the planned GCP provider.",
    "GOOGLE_CLOUD_PROJECT": "Google Cloud project ID recognized by Google Cloud SDKs.",
}
SETUP_ENV_VARS_BY_PROVIDER = {
    "aliyun": ["ALICLOUD_ACCESS_KEY_ID", "ALICLOUD_ACCESS_KEY_SECRET"],
    "aws": [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
    ],
    "gcp": ["GOOGLE_APPLICATION_CREDENTIALS", "GCP_PROJECT", "GOOGLE_CLOUD_PROJECT"],
}
SUPPORTED_SETUP_ENV_VARS = [
    env_name
    for provider in INIT_PROVIDER_CHOICES
    for env_name in SETUP_ENV_VARS_BY_PROVIDER[provider]
]


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


def preflight_provider_environment(*, dns_provider: str, deployer: str) -> None:
    """Print required env vars for init validation and fail early if any are missing."""
    namespaces = {_provider_namespace(dns_provider), _provider_namespace(deployer)}
    env_names: list[str] = []
    for namespace in sorted(namespaces):
        env_names.extend(_provider_env_vars(namespace))
    _emit_env_report(env_names, fail_on_missing=True)


def print_setup_environment_snapshot() -> None:
    """Print the env vars commonly used by supported providers before interactive setup starts."""
    _emit_env_report(SUPPORTED_SETUP_ENV_VARS, fail_on_missing=False)


def print_provider_environment_snapshot(provider: str) -> None:
    """Print the env vars commonly used by one provider before interactive setup starts."""
    _emit_env_report(SETUP_ENV_VARS_BY_PROVIDER.get(provider, []), fail_on_missing=False)


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
    if namespace == "aws":
        return {}
    return {}


def _runtime_provider_settings(namespace: str, deploy_settings: dict[str, Any]) -> dict[str, Any]:
    if namespace == "aliyun":
        access_key_id = os.getenv("ALICLOUD_ACCESS_KEY_ID")
        access_key_secret = os.getenv("ALICLOUD_ACCESS_KEY_SECRET")
        settings = {
            "access_key_id": access_key_id,
            "access_key_secret": access_key_secret,
        }
        region = os.getenv("ALICLOUD_REGION") or deploy_settings.get("region")
        if region:
            settings["region"] = region
        return settings
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


def preflight_config_environment(raw_data: dict[str, Any]) -> None:
    """Print env vars referenced by config and fail early if any are missing."""
    env_names = sorted(_find_env_placeholders(raw_data))
    if env_names:
        _emit_env_report(env_names, fail_on_missing=True)


def _emit_env_report(env_names: list[str], *, fail_on_missing: bool) -> None:
    if not env_names:
        return
    stream = sys.stderr
    stream.write("Environment variables used for this operation:\n")
    missing: list[str] = []
    for env_name in env_names:
        value = os.getenv(env_name)
        definition = ENV_VAR_DEFINITIONS.get(env_name, "Environment variable referenced by the configuration or provider setup.")
        stream.write(f"- {env_name}: {definition}\n")
        stream.write(f"  value: {_display_env_value(env_name, value)}\n")
        if value in (None, ""):
            missing.append(env_name)
    if missing and fail_on_missing:
        stream.write("\nMissing required environment variables:\n")
        for env_name in missing:
            stream.write(f"- {env_name}\n")
        raise ConfigError("Missing required environment variables. Set the variables listed above and retry.")


def _display_env_value(env_name: str, value: str | None) -> str:
    if value is None:
        return "<not set>"
    if _is_sensitive_env_name(env_name):
        return _redact_env_value(value)
    return value


def _is_sensitive_env_name(env_name: str) -> bool:
    sensitive_tokens = ("KEY", "SECRET", "TOKEN", "PASSWORD")
    env_tokens = env_name.upper().split("_")
    return any(token in env_tokens for token in sensitive_tokens)


def _redact_env_value(value: str) -> str:
    if len(value) <= 6:
        return "x" * len(value)
    return f"{value[:3]}{'x' * (len(value) - 6)}{value[-3:]}"


def _provider_env_vars(namespace: str) -> list[str]:
    if namespace == "aliyun":
        return ["ALICLOUD_ACCESS_KEY_ID", "ALICLOUD_ACCESS_KEY_SECRET"]
    if namespace == "aws":
        return []
    return []


def _find_env_placeholders(value: Any) -> set[str]:
    placeholders: set[str] = set()
    if isinstance(value, dict):
        for item in value.values():
            placeholders.update(_find_env_placeholders(item))
        return placeholders
    if isinstance(value, list):
        for item in value:
            placeholders.update(_find_env_placeholders(item))
        return placeholders
    if isinstance(value, str):
        current = value
        while "${" in current:
            start = current.find("${")
            end = current.find("}", start + 2)
            if end == -1:
                break
            placeholders.add(current[start + 2 : end])
            current = current[end + 1 :]
    return placeholders
