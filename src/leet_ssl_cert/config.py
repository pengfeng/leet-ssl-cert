"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import re
from typing import Any

import yaml

from .bootstrap import preflight_config_environment
from .errors import ConfigError

DEFAULT_DIRECTORY_URL = "https://acme-v02.api.letsencrypt.org/directory"
DEFAULT_STORAGE_DIR = Path.home() / ".leet-ssl-cert" / "certs"
DEFAULT_CONFIG_LOCATIONS = (
    Path("leet-ssl-cert.yaml"),
    Path.home() / ".leet-ssl-cert" / "config.yaml",
)
ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


@dataclass(slots=True)
class AccountConfig:
    email: str


@dataclass(slots=True)
class AcmeConfig:
    directory_url: str = DEFAULT_DIRECTORY_URL
    key_size: int = 2048
    renewal_days: int = 30
    dns_poll_attempts: int = 60
    dns_poll_interval: int = 10
    order_poll_timeout: int = 300


@dataclass(slots=True)
class StorageConfig:
    base_dir: Path = DEFAULT_STORAGE_DIR


@dataclass(slots=True)
class DeployTargetConfig:
    provider: str
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CertificateConfig:
    name: str
    domains: list[str]
    dns_provider: str
    deploy: list[DeployTargetConfig] = field(default_factory=list)


@dataclass(slots=True)
class AppConfig:
    account: AccountConfig
    acme: AcmeConfig
    storage: StorageConfig
    certificates: list[CertificateConfig]
    providers: dict[str, dict[str, Any]]
    path: Path


def resolve_config_path(path: str | Path | None = None) -> Path:
    """Resolve the configuration path using explicit or default locations."""
    if path is not None:
        config_path = Path(path).expanduser()
        if not config_path.exists():
            raise ConfigError(f"Config file not found: {config_path}")
        return config_path

    for candidate in DEFAULT_CONFIG_LOCATIONS:
        expanded = candidate.expanduser()
        if expanded.exists():
            return expanded

    searched = ", ".join(str(path.expanduser()) for path in DEFAULT_CONFIG_LOCATIONS)
    raise ConfigError(f"No config file found. Searched: {searched}")


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load and validate the project configuration."""
    config_path = resolve_config_path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw_data = yaml.safe_load(handle) or {}

    if not isinstance(raw_data, dict):
        raise ConfigError("Config root must be a mapping")

    preflight_config_environment(raw_data)
    interpolated = _interpolate_env(raw_data)
    config = _parse_config(interpolated, config_path)
    _validate_config(config)
    return config


def _parse_config(raw: dict[str, Any], path: Path) -> AppConfig:
    account_data = raw.get("account") or {}
    acme_data = raw.get("acme") or {}
    storage_data = raw.get("storage") or {}
    certificates_data = raw.get("certificates") or []
    providers_data = raw.get("providers") or {}

    account = AccountConfig(email=str(account_data.get("email", "")).strip())

    acme = AcmeConfig(
        directory_url=str(acme_data.get("directory_url", DEFAULT_DIRECTORY_URL)),
        key_size=int(acme_data.get("key_size", 2048)),
        renewal_days=int(acme_data.get("renewal_days", 30)),
        dns_poll_attempts=int(acme_data.get("dns_poll_attempts", 60)),
        dns_poll_interval=int(acme_data.get("dns_poll_interval", 10)),
        order_poll_timeout=int(acme_data.get("order_poll_timeout", 300)),
    )

    storage = StorageConfig(
        base_dir=Path(
            str(storage_data.get("base_dir", DEFAULT_STORAGE_DIR))
        ).expanduser(),
    )

    certificates: list[CertificateConfig] = []
    for item in certificates_data:
        if not isinstance(item, dict):
            raise ConfigError("Each certificate entry must be a mapping")
        deploy_targets = []
        for deploy_item in item.get("deploy", []) or []:
            if not isinstance(deploy_item, dict):
                raise ConfigError("Each deploy target must be a mapping")
            provider = str(deploy_item.get("provider", "")).strip()
            settings = {
                key: value for key, value in deploy_item.items() if key != "provider"
            }
            deploy_targets.append(
                DeployTargetConfig(provider=provider, settings=settings)
            )
        certificates.append(
            CertificateConfig(
                name=str(item.get("name", "")).strip(),
                domains=[
                    str(domain).strip() for domain in item.get("domains", []) or []
                ],
                dns_provider=str(item.get("dns_provider", "")).strip(),
                deploy=deploy_targets,
            )
        )

    providers = {
        str(provider_name): dict(provider_settings or {})
        for provider_name, provider_settings in providers_data.items()
    }

    return AppConfig(
        account=account,
        acme=acme,
        storage=storage,
        certificates=certificates,
        providers=providers,
        path=path,
    )


def _validate_config(config: AppConfig) -> None:
    if not config.account.email:
        raise ConfigError("account.email is required")
    if "@" not in config.account.email:
        raise ConfigError("account.email must look like an email address")
    if config.acme.key_size < 2048:
        raise ConfigError("acme.key_size must be at least 2048")
    if config.acme.renewal_days < 1:
        raise ConfigError("acme.renewal_days must be positive")
    if config.acme.dns_poll_attempts < 1:
        raise ConfigError("acme.dns_poll_attempts must be positive")
    if config.acme.dns_poll_interval < 0:
        raise ConfigError("acme.dns_poll_interval must be zero or greater")
    if not config.certificates:
        raise ConfigError("At least one certificate must be configured")

    names: set[str] = set()
    for certificate in config.certificates:
        if not certificate.name:
            raise ConfigError("certificate.name is required")
        if certificate.name in names:
            raise ConfigError(f"Duplicate certificate name: {certificate.name}")
        names.add(certificate.name)
        if not certificate.domains:
            raise ConfigError(
                f"certificate {certificate.name!r} must define at least one domain"
            )
        if not certificate.dns_provider:
            raise ConfigError(
                f"certificate {certificate.name!r} must define dns_provider"
            )
        for target in certificate.deploy:
            if not target.provider:
                raise ConfigError(
                    f"certificate {certificate.name!r} has a deploy target without provider"
                )


def _interpolate_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _interpolate_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_interpolate_env(item) for item in value]
    if isinstance(value, str):
        return ENV_VAR_PATTERN.sub(_resolve_env_var, value)
    return value


def _resolve_env_var(match: re.Match[str]) -> str:
    env_name = match.group(1)
    if env_name not in os.environ:
        raise ConfigError(f"Environment variable {env_name} is not set")
    return os.environ[env_name]
