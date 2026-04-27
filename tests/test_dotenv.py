"""Tests for the minimal .env loader."""

from __future__ import annotations

from pathlib import Path

from leet_ssl_cert.dotenv import _parse_line, load_dotenv_files


def test_parse_line_handles_basic_assignments() -> None:
    assert _parse_line("FOO=bar") == ("FOO", "bar")
    assert _parse_line("  FOO = bar  ") == ("FOO", "bar")


def test_parse_line_strips_export_prefix() -> None:
    assert _parse_line("export FOO=bar") == ("FOO", "bar")


def test_parse_line_strips_quotes() -> None:
    assert _parse_line('FOO="bar baz"') == ("FOO", "bar baz")
    assert _parse_line("FOO='bar baz'") == ("FOO", "bar baz")


def test_parse_line_strips_inline_comment_for_unquoted() -> None:
    assert _parse_line("FOO=bar # note") == ("FOO", "bar")


def test_parse_line_keeps_hash_inside_quoted_value() -> None:
    assert _parse_line('FOO="bar #not-a-comment"') == ("FOO", "bar #not-a-comment")


def test_parse_line_skips_blank_and_comment_lines() -> None:
    assert _parse_line("") == (None, "")
    assert _parse_line("   ") == (None, "")
    assert _parse_line("# hello") == (None, "")


def test_parse_line_rejects_invalid_keys() -> None:
    assert _parse_line("1FOO=bar") == (None, "")
    assert _parse_line("=bar") == (None, "")
    assert _parse_line("FO O=bar") == (None, "")


def test_load_dotenv_files_populates_environ_without_overriding(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALREADY_SET=from-file\n"
        "NEW_KEY=hello\n"
        "QUOTED=\"with spaces\"\n",
        encoding="utf-8",
    )

    environ: dict[str, str] = {"ALREADY_SET": "from-environ"}
    applied = load_dotenv_files((env_file,), environ=environ)

    assert applied == {"NEW_KEY": "hello", "QUOTED": "with spaces"}
    assert environ["ALREADY_SET"] == "from-environ"
    assert environ["NEW_KEY"] == "hello"
    assert environ["QUOTED"] == "with spaces"


def test_load_dotenv_files_first_file_wins(tmp_path: Path) -> None:
    first = tmp_path / "a.env"
    second = tmp_path / "b.env"
    first.write_text("KEY=first\n", encoding="utf-8")
    second.write_text("KEY=second\nOTHER=both\n", encoding="utf-8")

    environ: dict[str, str] = {}
    load_dotenv_files((first, second), environ=environ)

    assert environ == {"KEY": "first", "OTHER": "both"}


def test_load_dotenv_files_silently_skips_missing_paths(tmp_path: Path) -> None:
    missing = tmp_path / "nope.env"
    environ: dict[str, str] = {}
    applied = load_dotenv_files((missing,), environ=environ)
    assert applied == {}
    assert environ == {}
