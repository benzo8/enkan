from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from enkan.config import (
    AppConfig,
    Config,
    CONFIG_KEYS,
    CONFIG_KEYS_BY_NAME,
    CONFIG_KEYS_BY_TOML_TABLE,
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

    assert app_config.values.get("mode") is None
    assert app_config.values.get("random") is None
    assert config("navigation_basis") in {"folder", "branch"}
    assert config("cache.policy") == "cache-all"
    assert config("cache.max_bytes") == 100 * 1024 * 1024


def test_config_registry_keys_are_complete():
    assert CONFIG_KEYS
    assert set(CONFIG_KEYS_BY_NAME) == {key.name for key in CONFIG_KEYS}

    for key in CONFIG_KEYS:
        assert key.name
        assert key.toml_table
        assert key.toml_key
        assert callable(key.parser)
        assert key.scope in {"build", "runtime", "both"}
        assert key.parser(key.default) == key.default or key.default is None


def test_config_registry_groups_toml_keys_by_table():
    grouped = {
        table: {key.toml_key for key in keys}
        for table, keys in CONFIG_KEYS_BY_TOML_TABLE.items()
    }

    assert grouped["slideshow"] >= {
        "mode",
        "random",
        "dont_recurse",
        "video",
        "mute",
        "navigation_basis",
    }
    assert grouped["progress"] == {"quiet"}
    assert grouped["cache"] == {"background_preload", "policy", "max_bytes"}


def test_load_app_config_accepts_every_registered_toml_key(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
mode = "b2"
random = true
dont_recurse = true
video = false
mute = false
navigation_basis = "branch"

[progress]
quiet = true

[cache]
background_preload = true
policy = "bounded-bytes"
max_bytes = 4096
""".strip(),
        encoding="utf-8",
    )

    config = Config(app_config=load_app_config(str(config_path)))

    for key in CONFIG_KEYS:
        assert config(key.name) is not None or key.default is None


def test_load_app_config_reads_slideshow_and_cache_sections(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
mode = "B2"
random = true
video = false
navigation_basis = "folder"

[progress]
quiet = true

[cache]
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
    assert config("progress.quiet") is True
    assert config("navigation_basis") == "folder"
    assert config("cache.policy") == "bounded-bytes"
    assert config("cache.max_bytes") == 2048


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


def test_load_app_config_rejects_unknown_root_table(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[other]
value = true
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Unknown root key"):
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

[progress]
quiet = ["nope"]

[cache]
background_preload = "sure"
policy = "forever"
max_bytes = -1
""".strip(),
        encoding="utf-8",
    )

    config = Config(app_config=load_app_config(str(config_path)))

    assert config("random") is False
    assert config("video") is True
    assert config("progress.quiet") is False
    assert config("cache.background_preload") is True
    assert config("cache.policy") == "cache-all"
    assert config("cache.max_bytes") == 100 * 1024 * 1024


def test_load_app_config_falls_back_for_missing_known_values(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text("[slideshow]\n", encoding="utf-8")

    config = Config(app_config=load_app_config(str(config_path)))

    assert config("navigation_basis") == "folder"
    assert config("cache.policy") == "cache-all"
    assert config("cache.max_bytes") == 100 * 1024 * 1024


def test_config_facade_preserves_cli_precedence():
    app_config = AppConfig(
        values={
            "mode": "b1",
            "random": True,
            "video": False,
            "progress.quiet": False,
            "cache.background_preload": True,
            "navigation_basis": "branch",
        }
    )
    args = Namespace(
        mode="b3",
        random=None,
        dont_recurse=None,
        video=None,
        mute=None,
        quiet=True,
        no_background=True,
        navigation_basis="folder",
    )

    config = Config(app_config=app_config, args=args)

    assert config("mode") == "b3"
    assert config("random") is True
    assert config("video") is False
    assert config("progress.quiet") is True
    assert config("cache.background_preload") is False
    assert config("navigation_basis") == "folder"


def test_config_facade_applies_runtime_overrides_last():
    config = Config(
        app_config=AppConfig(values={"navigation_basis": "branch"})
    ).with_runtime_overrides(
        navigation_basis="folder",
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
