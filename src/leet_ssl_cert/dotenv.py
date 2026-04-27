"""Minimal .env loader.

Reads simple ``KEY=value`` lines from ``.env`` files and populates
``os.environ`` with any keys that are not already set. Existing process
environment variables always win; this is a defaults mechanism, not an
override.

Supported syntax:
- ``KEY=value`` lines.
- ``export KEY=value`` (the ``export`` prefix is stripped).
- Single- or double-quoted values; quotes are stripped.
- Lines beginning with ``#`` are comments. Blank lines are ignored.
- Inline comments after an unquoted value (``KEY=value  # note``) are stripped.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DOTENV_LOCATIONS = (
    Path(".env"),
    Path.home() / ".leet-ssl-cert" / ".env",
)


def load_dotenv_files(
    locations: tuple[Path, ...] = DEFAULT_DOTENV_LOCATIONS,
    *,
    environ: dict[str, str] | None = None,
) -> dict[str, str]:
    """Load every existing ``.env`` file from ``locations``.

    Returns the keys that were applied to ``environ`` (or ``os.environ``
    when ``environ`` is None). The first occurrence of a key wins, both
    within a single file and across files; existing environ entries
    always take precedence over file values.
    """
    target = os.environ if environ is None else environ
    applied: dict[str, str] = {}
    for location in locations:
        path = location.expanduser()
        if not path.is_file():
            continue
        for key, value in _parse_dotenv(path).items():
            if key in target or key in applied:
                continue
            applied[key] = value
            target[key] = value
    return applied


def _parse_dotenv(path: Path) -> dict[str, str]:
    pairs: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            key, value = _parse_line(raw_line)
            if key is None:
                continue
            pairs.setdefault(key, value)
    return pairs


def _parse_line(raw_line: str) -> tuple[str | None, str]:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None, ""
    if line.startswith("export "):
        line = line[len("export ") :].lstrip()
    if "=" not in line:
        return None, ""
    key, _, value = line.partition("=")
    key = key.strip()
    if not key or not _is_valid_key(key):
        return None, ""
    value = value.strip()
    if value and value[0] in ("'", '"') and value.endswith(value[0]) and len(value) >= 2:
        value = value[1:-1]
    else:
        comment_index = value.find(" #")
        if comment_index >= 0:
            value = value[:comment_index].rstrip()
    return key, value


def _is_valid_key(key: str) -> bool:
    if not key:
        return False
    if not (key[0].isalpha() or key[0] == "_"):
        return False
    return all(ch.isalnum() or ch == "_" for ch in key)
