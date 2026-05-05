from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from enkan.config import (
    AppConfig,
    Config,
    ConfigError,
    DEFAULT_CONFIG_FILENAME,
    discover_config_path,
    load_app_config,
)


def test_load_app_config_falls_back_to_app_folder_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata_empty"))

    app_config = load_app_config()
    config = Config(app_config=app_config)

    assert app_config.mode is None
    assert app_config.random is None
    assert config("navigation_basis") in {"folder", "branch"}
    assert config("video_cache.policy") == "cache-all"
    assert config("video_cache.max_bytes") == 100 * 1024 * 1024


def test_load_app_config_reads_slideshow_and_video_cache_sections(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
mode = "B2"
random = true
video = false
quiet = true
navigation_basis = "folder"

[video_cache]
policy = "bounded-bytes"
max_bytes = 2048
""".strip(),
        encoding="utf-8",
    )

    app_config = load_app_config(str(config_path))
    config = Config(app_config=app_config)

    assert config("mode") == "b2"
    assert config("random") is True
    assert config("video") is False
    assert config("quiet") is True
    assert config("navigation_basis") == "folder"
    assert config("video_cache.policy") == "bounded-bytes"
    assert config("video_cache.max_bytes") == 2048


def test_config_facade_uses_explicit_branch_navigation_basis(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
navigation_basis = "branch"
""".strip(),
        encoding="utf-8",
    )

    config = Config(app_config=load_app_config(str(config_path)))

    assert config("navigation_basis") == "branch"


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


def test_load_app_config_falls_back_for_invalid_mode(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
mode = "not-a-mode"
""".strip(),
        encoding="utf-8",
    )

    config = Config(app_config=load_app_config(str(config_path)))

    assert config("mode") is None


def test_load_app_config_falls_back_for_invalid_navigation_basis(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
navigation_basis = "node"
""".strip(),
        encoding="utf-8",
    )

    config = Config(app_config=load_app_config(str(config_path)))

    assert config("navigation_basis") == "folder"


def test_load_app_config_falls_back_for_invalid_known_values(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
random = "yes"
video = 12
quiet = ["nope"]

[video_cache]
policy = "forever"
max_bytes = -1
""".strip(),
        encoding="utf-8",
    )

    config = Config(app_config=load_app_config(str(config_path)))

    assert config("random") is False
    assert config("video") is True
    assert config("quiet") is False
    assert config("video_cache.policy") == "cache-all"
    assert config("video_cache.max_bytes") == 100 * 1024 * 1024


def test_load_app_config_falls_back_for_missing_known_values(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text("[slideshow]\n", encoding="utf-8")

    config = Config(app_config=load_app_config(str(config_path)))

    assert config("navigation_basis") == "folder"
    assert config("video_cache.policy") == "cache-all"
    assert config("video_cache.max_bytes") == 100 * 1024 * 1024


def test_config_facade_preserves_cli_precedence():
    app_config = AppConfig(
        mode="b1",
        random=True,
        video=False,
        quiet=False,
        no_background=True,
        navigation_basis="branch",
    )
    args = Namespace(
        mode="b3",
        random=None,
        dont_recurse=None,
        video=None,
        mute=None,
        quiet=True,
        no_background=None,
        navigation_basis="folder",
    )

    config = Config(app_config=app_config, args=args)

    assert config("mode") == "b3"
    assert config("random") is True
    assert config("video") is False
    assert config("quiet") is True
    assert config("no_background") is True
    assert config("navigation_basis") == "folder"


def test_config_facade_applies_runtime_overrides_last():
    config = Config(app_config=AppConfig(navigation_basis="branch")).with_runtime_overrides(
        navigation_basis="folder"
    )

    assert config("navigation_basis") == "folder"


def test_config_facade_rejects_unknown_lookup_key():
    config = Config()

    with pytest.raises(KeyError):
        config("missing")


def _write_minimal_config(
    directory: Path, mode: str = "b1", navigation_basis: str | None = None
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / DEFAULT_CONFIG_FILENAME
    lines = ["[slideshow]", f'mode = "{mode}"']
    if navigation_basis is not None:
        lines.append(f'navigation_basis = "{navigation_basis}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_discover_config_finds_app_folder_as_final_fallback(tmp_path, monkeypatch):
    from enkan import config as config_module

    start = tmp_path / "start"
    start.mkdir()
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata_empty"))
    expected = Path(config_module.__file__).resolve().parent / DEFAULT_CONFIG_FILENAME

    result = discover_config_path(start_folder=start)

    assert result == expected


def test_discover_config_finds_start_folder_first(tmp_path, monkeypatch):
    start = tmp_path / "start"
    user = tmp_path / "appdata" / "enkan"
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    expected = _write_minimal_config(start, mode="b1")
    _write_minimal_config(user, mode="b2")

    result = discover_config_path(start_folder=start)

    assert result == expected.resolve()


def test_discover_config_falls_back_to_user_config(tmp_path, monkeypatch):
    start = tmp_path / "start"
    start.mkdir()
    user = tmp_path / "appdata" / "enkan"
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    expected = _write_minimal_config(user, mode="b2")

    result = discover_config_path(start_folder=start)

    assert result == expected.resolve()


def test_discover_config_uses_cwd_as_default_start_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata_empty"))
    expected = _write_minimal_config(tmp_path, mode="b3")

    result = discover_config_path()

    assert result == expected.resolve()


def test_discover_config_explicit_path_bypasses_discovery(tmp_path, monkeypatch):
    start = tmp_path / "start"
    start.mkdir()
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata_empty"))
    explicit = tmp_path / "custom" / "enkan.toml"
    explicit.parent.mkdir()
    explicit.write_text('[slideshow]\nmode = "b4"\n', encoding="utf-8")

    config = Config(app_config=load_app_config(str(explicit), start_folder=start))

    assert config("mode") == "b4"


def test_discover_config_explicit_path_missing_raises(tmp_path):
    missing = tmp_path / "nonexistent" / "enkan.toml"

    with pytest.raises(ConfigError, match="not found"):
        load_app_config(str(missing))
