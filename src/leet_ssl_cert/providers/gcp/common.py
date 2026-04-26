"""Shared helpers for GCP providers."""

from __future__ import annotations

import os
from typing import Any


def resolve_gcp_project(settings: dict[str, Any]) -> str | None:
    """Resolve the active GCP project from settings, env, or ADC defaults."""
    configured = str(settings.get("project", "")).strip()
    if configured:
        return configured

    env_value = str(os.getenv("GOOGLE_CLOUD_PROJECT", "")).strip()
    if env_value:
        return env_value

    try:
        import google.auth
    except ImportError:
        return None

    try:
        _, project = google.auth.default()
    except Exception:
        return None
    return str(project).strip() or None


def extract_resource_name(resource_path: str | None) -> str | None:
    """Return the final path component from a self-link style resource path."""
    if not resource_path:
        return None
    return resource_path.rstrip("/").rsplit("/", 1)[-1]
