"""Cron schedule helpers."""

from __future__ import annotations

from pathlib import Path


def build_cron_entry(schedule: str, config_path: Path) -> str:
    """Return the cron entry for periodic renewal."""
    return f"{schedule} leet-ssl-cert run --config {config_path.expanduser()}"
