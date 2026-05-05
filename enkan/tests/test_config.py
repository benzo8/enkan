from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from enkan.config import (
    AppConfig,
    ConfigError,
    DEFAULT_CONFIG_FILENAME,
    discover_config_path,
    load_app_config,
    merge_config_into_args,
)


def test_load_app_config_uses_defaults_when_default_file_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config = load_app_config()

    assert config.mode is None
    assert config.random is None
    assert config.video_cache.policy == "cache-all"
    assert config.video_cache.max_bytes == 100 * 1024 * 1024


def test_load_app_config_reads_slideshow_and_video_cache_sections(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
mode = "B2"
random = true
video = false
quiet = true

[video_cache]
policy = "bounded-bytes"
max_bytes = 2048
""".strip(),
        encoding="utf-8",
    )

    config = load_app_config(str(config_path))

    assert config.mode == "b2"
    assert config.random is True
    assert config.video is False
    assert config.quiet is True
    assert config.video_cache.policy == "bounded-bytes"
    assert config.video_cache.max_bytes == 2048


def test_load_app_config_rejects_unknown_keys(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
mode = "b1"
unexpected = true
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Unknown slideshow key"):
        load_app_config(str(config_path))


def test_load_app_config_rejects_invalid_mode(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
mode = "not-a-mode"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Invalid slideshow.mode"):
        load_app_config(str(config_path))


def test_merge_config_into_args_preserves_cli_precedence():
    args = Namespace(
        mode="b3",
        random=None,
        dont_recurse=None,
        video=None,
        mute=None,
        quiet=True,
        no_background=None,
    )
    config = AppConfig(
        mode="b1",
        random=True,
        video=False,
        quiet=False,
        no_background=True,
    )

    merged = merge_config_into_args(args, config)

    assert merged.mode == "b3"
    assert merged.random is True
    assert merged.video is False
    assert merged.quiet is True
    assert merged.no_background is True


# ---------------------------------------------------------------------------
# Config discovery order tests
# ---------------------------------------------------------------------------

def _write_minimal_config(directory: Path, mode: str = "b1") -> Path:
    """Write a minimal valid enkan.toml to directory and return the path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / DEFAULT_CONFIG_FILENAME
    path.write_text(f'[slideshow]\nmode = "{mode}"\n', encoding="utf-8")
    return path


def test_discover_config_path_returns_none_when_no_file_exists(tmp_path, monkeypatch):
    """Returns None when enkan.toml is absent from all search locations."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    result = discover_config_path(start_folder=tmp_path / "start")

    assert result is None


def test_discover_config_finds_start_folder_first(tmp_path, monkeypatch):
    """Start folder is checked before user config and app folder."""
    start = tmp_path / "start"
    user = tmp_path / "appdata" / "enkan"
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    expected = _write_minimal_config(start, mode="b1")
    _write_minimal_config(user, mode="b2")

    result = discover_config_path(start_folder=start)

    assert result == expected.resolve()


def test_discover_config_falls_back_to_user_config(tmp_path, monkeypatch):
    """User config folder is used when start folder has no config."""
    start = tmp_path / "start"
    start.mkdir()
    user = tmp_path / "appdata" / "enkan"
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    expected = _write_minimal_config(user, mode="b2")

    result = discover_config_path(start_folder=start)

    assert result == expected.resolve()


def test_discover_config_uses_cwd_as_default_start_folder(tmp_path, monkeypatch):
    """When start_folder is not supplied, CWD is used as the start folder."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata_empty"))
    expected = _write_minimal_config(tmp_path, mode="b3")

    result = discover_config_path()

    assert result == expected.resolve()


def test_discover_config_explicit_path_bypasses_discovery(tmp_path, monkeypatch):
    """--config explicit path is used directly; discovery is skipped."""
    start = tmp_path / "start"
    start.mkdir()
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata_empty"))
    explicit = tmp_path / "custom" / "enkan.toml"
    explicit.parent.mkdir()
    explicit.write_text('[slideshow]\nmode = "b4"\n', encoding="utf-8")

    config = load_app_config(str(explicit), start_folder=start)

    assert config.mode == "b4"


def test_discover_config_explicit_path_missing_raises(tmp_path):
    """Explicit --config path that does not exist raises ConfigError."""
    missing = tmp_path / "nonexistent" / "enkan.toml"

    with pytest.raises(ConfigError, match="not found"):
        load_app_config(str(missing))