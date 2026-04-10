from __future__ import annotations

from pathlib import Path

import pytest

from leet_ssl_cert.config import load_config
from leet_ssl_cert.errors import ConfigError


def test_load_config_interpolates_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
account:
  email: admin@example.com
storage:
  base_dir: ./state/certs
certificates:
  - name: site
    domains: [example.com]
    dns_provider: aliyun
providers:
  aliyun:
    access_key_id: ${TEST_ACCESS_KEY}
    access_key_secret: static-secret
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_ACCESS_KEY", "resolved-key")

    config = load_config(config_path)

    assert config.providers["aliyun"]["access_key_id"] == "resolved-key"
    assert config.storage.base_dir == Path("./state/certs").expanduser()


def test_load_config_requires_env_var(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
account:
  email: admin@example.com
certificates:
  - name: site
    domains: [example.com]
    dns_provider: aliyun
providers:
  aliyun:
    access_key_id: ${MISSING_ENV}
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Missing required environment variables"):
        load_config(config_path)


def test_load_config_reports_used_env_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
account:
  email: admin@example.com
certificates:
  - name: site
    domains: [example.com]
    dns_provider: aliyun
providers:
  aliyun:
    access_key_id: ${TEST_ACCESS_KEY}
    access_key_secret: static-secret
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_ACCESS_KEY", "resolved-key")

    load_config(config_path)

    captured = capsys.readouterr()
    assert "TEST_ACCESS_KEY" in captured.err
    assert "value: resxxxxxxkey" in captured.err
    assert "resolved-key" not in captured.err
