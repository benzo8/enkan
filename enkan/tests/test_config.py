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
from enkan.utils.BuildState import BuildState
from enkan.utils.argparse_setup import get_arg_parser


def test_load_app_config_falls_back_to_app_folder_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata_empty"))

    app_config = load_app_config()
    config = Config(app_config=app_config)

    assert app_config.values.get("slideshow.mode") is None
    assert app_config.values.get("slideshow.provider") == "weighted"
    assert config("slideshow.navigation_basis") in {"folder", "branch"}
    assert config("cache.policy") == "cache-all"
    assert config("cache.max_bytes") == 100 * 1024 * 1024


def test_config_registry_keys_are_complete():
    assert CONFIG_KEYS
    assert set(CONFIG_KEYS_BY_NAME) == {key.name for key in CONFIG_KEYS}

    for key in CONFIG_KEYS:
        assert key.name == f"{key.toml_table}.{key.toml_key}"
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
        "provider",
        "video",
        "mute",
        "navigation_basis",
        "interval",
        "auto",
    }
    assert grouped["progress"] == {"quiet"}
    assert grouped["cache"] == {
        "background_preload",
        "policy",
        "max_bytes",
        "preload_queue_length",
        "cache_size",
        "history_queue_length",
    }


def test_load_app_config_accepts_every_registered_toml_key(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
mode = "b2"
provider = "CRW"
video = false
mute = false
navigation_basis = "branch"
interval = 7500
auto = true

[progress]
quiet = true

[cache]
background_preload = true
policy = "bounded-bytes"
max_bytes = 4096
preload_queue_length = 4
cache_size = 12
history_queue_length = 30
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
provider = "random"
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

    assert config("slideshow.mode") == "b2"
    assert config("slideshow.provider") == "random"
    assert config("slideshow.video") is False
    assert config("progress.quiet") is True
    assert config("slideshow.navigation_basis") == "folder"
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

    assert config("slideshow.navigation_basis") == "branch"


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


def test_load_app_config_rejects_build_only_dont_recurse_key(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
dont_recurse = true
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

    assert config("slideshow.mode") is None


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

    assert config("slideshow.navigation_basis") == "folder"


def test_load_app_config_falls_back_for_invalid_known_values(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
provider = "shuffle"
video = 12

[progress]
quiet = ["nope"]

[cache]
background_preload = "sure"
policy = "forever"
max_bytes = -1
preload_queue_length = 0
cache_size = "large"
history_queue_length = false
""".strip(),
        encoding="utf-8",
    )

    config = Config(app_config=load_app_config(str(config_path)))

    assert config("slideshow.provider") == "weighted"
    assert config("slideshow.video") is True
    assert config("progress.quiet") is False
    assert config("cache.background_preload") is True
    assert config("cache.policy") == "cache-all"
    assert config("cache.max_bytes") == 100 * 1024 * 1024
    assert config("cache.preload_queue_length") == 3
    assert config("cache.cache_size") == 10
    assert config("cache.history_queue_length") == 25


def test_load_app_config_falls_back_for_missing_known_values(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text("[slideshow]\n", encoding="utf-8")

    config = Config(app_config=load_app_config(str(config_path)))

    assert config("slideshow.navigation_basis") == "folder"
    assert config("slideshow.provider") == "weighted"
    assert config("cache.policy") == "cache-all"
    assert config("cache.max_bytes") == 100 * 1024 * 1024
    assert config("cache.preload_queue_length") == 3
    assert config("cache.cache_size") == 10
    assert config("cache.history_queue_length") == 25


def test_config_facade_preserves_cli_precedence():
    app_config = AppConfig(
        values={
            "slideshow.mode": "b1",
            "slideshow.provider": "random",
            "slideshow.video": False,
            "progress.quiet": False,
            "cache.background_preload": True,
            "slideshow.navigation_basis": "branch",
        }
    )
    args = Namespace(
        **{
            "slideshow.mode": "b3",
            "slideshow.provider": None,
            "slideshow.video": None,
            "slideshow.mute": None,
            "progress.quiet": True,
            "cache.background_preload": False,
            "slideshow.navigation_basis": "folder",
        }
    )

    config = Config(app_config=app_config, args=args)

    assert config("slideshow.mode") == "b3"
    assert config("slideshow.provider") == "random"
    assert config("slideshow.video") is False
    assert config("progress.quiet") is True
    assert config("cache.background_preload") is False
    assert config("slideshow.navigation_basis") == "folder"


def test_config_facade_reports_cli_override():
    args = Namespace(**{"slideshow.mode": "b3"})
    config = Config(app_config=AppConfig(values={"slideshow.mode": "b1"}), args=args)

    assert config.is_cli_override("slideshow.mode") is True
    assert config.is_cli_override("slideshow.video") is False


def test_build_state_treats_toml_mode_as_default_not_cli_pin():
    config = Config(app_config=AppConfig(values={"slideshow.mode": "b2"}))
    build_state = BuildState.from_config(
        config,
        cli_mode_pinned=config.is_cli_override("slideshow.mode"),
    )

    assert build_state.mode == {2: ("b", [0, 0])}
    assert build_state.cli_mode is None
    assert build_state.cli_mode_pinned is False


def test_build_state_records_cli_pinned_mode():
    args = Namespace(**{"slideshow.mode": "b3"})
    config = Config(app_config=AppConfig(values={"slideshow.mode": "b2"}), args=args)
    build_state = BuildState.from_config(
        config,
        cli_mode_pinned=config.is_cli_override("slideshow.mode"),
    )

    assert build_state.mode == {3: ("b", [0, 0])}
    assert build_state.cli_mode == {3: ("b", [0, 0])}
    assert build_state.cli_mode_pinned is True


def test_config_facade_rejects_unknown_lookup_key():
    config = Config()

    with pytest.raises(KeyError):
        config("missing")


def test_config_facade_rejects_old_unqualified_lookup_key():
    config = Config()

    with pytest.raises(KeyError):
        config("navigation_basis")


def test_argparse_generation_includes_registered_config_flags():
    parser = get_arg_parser()
    option_strings = set(parser._option_string_actions)

    for key in CONFIG_KEYS:
        for entry in key.argparse_entries:
            assert set(entry.flags) <= option_strings


def test_argparse_navigation_basis_feeds_config():
    args = get_arg_parser().parse_args(["--navigation-basis", "branch"])
    config = Config(args=args)

    assert config("slideshow.navigation_basis") == "branch"


def test_argparse_navigation_basis_short_alias_feeds_config():
    args = get_arg_parser().parse_args(["--nb", "branch"])
    config = Config(args=args)

    assert config("slideshow.navigation_basis") == "branch"


def test_argparse_provider_feeds_config():
    args = get_arg_parser().parse_args(["--provider", "burst"])
    config = Config(args=args)

    assert config("slideshow.provider") == "burst"


def test_argparse_provider_accepts_crw_alias():
    args = get_arg_parser().parse_args(["--provider", "CRW"])
    config = Config(args=args)

    assert config("slideshow.provider") == "controlled_random_weighted"


def test_argparse_random_feeds_provider_config():
    args = get_arg_parser().parse_args(["--random"])
    config = Config(args=args)

    assert config("slideshow.provider") == "random"


def test_argparse_rejects_invalid_registry_value():
    parser = get_arg_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--navigation-basis", "node"])


def test_argparse_no_recurse_is_manual_build_flag():
    args = get_arg_parser().parse_args(["--no-recurse"])

    assert args.no_recurse is True
    assert not hasattr(args, "slideshow.dont_recurse")


def test_argparse_no_recurse_short_alias_is_manual_build_flag():
    args = get_arg_parser().parse_args(["--nr"])

    assert args.no_recurse is True


def test_argparse_no_background_feeds_positive_config_key():
    args = get_arg_parser().parse_args(["--no-background"])
    config = Config(args=args)

    assert config("cache.background_preload") is False


def test_argparse_background_preload_feeds_positive_config_key():
    args = get_arg_parser().parse_args(["--background-preload"])
    config = Config(args=args)

    assert config("cache.background_preload") is True


def test_argparse_interval_feeds_config_as_positive_int():
    args = get_arg_parser().parse_args(["--interval", "7500"])
    config = Config(args=args)

    assert config("slideshow.interval") == 7500
    assert config("slideshow.auto") is False


def test_argparse_auto_starts_with_default_interval():
    args = get_arg_parser().parse_args(["--auto"])
    config = Config(args=args)

    assert config("slideshow.auto") is True
    assert config("slideshow.interval") == 10000


def test_argparse_auto_optional_interval_feeds_config():
    parser = get_arg_parser()

    auto_config = Config(args=parser.parse_args(["--auto", "7500"]))
    short_config = Config(args=parser.parse_args(["-a", "7500"]))

    assert auto_config("slideshow.auto") is True
    assert short_config("slideshow.auto") is True
    assert auto_config("slideshow.interval") == 7500
    assert short_config("slideshow.interval") == 7500


def test_argparse_interval_and_auto_are_composable():
    args = get_arg_parser().parse_args(["--interval", "7500", "--auto"])
    config = Config(args=args)

    assert config("slideshow.auto") is True
    assert config("slideshow.interval") == 7500


def test_argparse_does_not_generate_cache_sizing_flags():
    parser = get_arg_parser()
    option_strings = set(parser._option_string_actions)

    assert "--cache-size" not in option_strings
    assert "--preload-queue-length" not in option_strings
    assert "--history-queue-length" not in option_strings


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

    assert config("slideshow.mode") == "b4"


def test_discover_config_explicit_path_missing_raises(tmp_path):
    missing = tmp_path / "nonexistent" / "enkan.toml"

    with pytest.raises(ConfigError, match="not found"):
        load_app_config(str(missing))
