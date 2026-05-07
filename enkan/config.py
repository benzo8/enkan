from __future__ import annotations

import os
import argparse
from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Literal
import tomllib

from enkan.constants import CX_PATTERN

DEFAULT_CONFIG_FILENAME = "enkan.toml"
ConfigScope = Literal["build", "runtime", "both"]
ConfigParser = Callable[[Any], Any | None]


class ConfigError(ValueError):
    """Raised when persisted configuration cannot be loaded or validated."""


def parse_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def parse_mode(value: Any) -> str | None:
    return value.lower() if isinstance(value, str) and CX_PATTERN.fullmatch(value) else None


def parse_choice(*choices: str) -> ConfigParser:
    allowed = set(choices)

    def parser(value: Any) -> str | None:
        return value if isinstance(value, str) and value in allowed else None

    return parser


def parse_provider(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalised = value.lower()
    aliases = {
        "crw": "controlled_random_weighted",
        "controlled_random_weighted": "controlled_random_weighted",
        "wgt": "weighted",
        "weighted": "weighted",
        "bur": "burst",
        "burst": "burst",
        "rnd": "random",
        "random": "random",
    }
    return aliases.get(normalised)


def parse_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdecimal():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


@dataclass(frozen=True)
class ArgparseEntry:
    flags: tuple[str, ...]
    dest: str | None = None
    action: Any = None
    const: Any = None
    choices: tuple[str, ...] = ()
    help: str | None = None
    metavar: str | None = None
    nargs: str | int | None = None


def entries(*names: str, **kwargs: Any) -> tuple[ArgparseEntry, ...]:
    return (ArgparseEntry(tuple(_argparse_flag(name) for name in names), **kwargs),)


def _argparse_flag(name: str) -> str:
    if name.startswith("-"):
        return name
    return f"--{name.replace('_', '-')}"


class AutoAdvanceAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        setattr(namespace, "slideshow.auto", True)
        if values is None:
            return
        parsed = parse_positive_int(values)
        if parsed is None:
            raise argparse.ArgumentTypeError(
                f"invalid slideshow.interval value: {values!r}"
            )
        setattr(namespace, "slideshow.interval", parsed)


@dataclass(frozen=True)
class ConfigKey:
    toml_table: str
    toml_key: str
    default: Any
    parser: ConfigParser
    argparse_entries: tuple[ArgparseEntry, ...] = ()
    choices: tuple[str, ...] = ()
    scope: ConfigScope = "both"
    invalid_fallback: bool = True

    @property
    def name(self) -> str:
        return f"{self.toml_table}.{self.toml_key}"


@dataclass(frozen=True)
class AppConfig:
    values: dict[str, Any] = field(default_factory=dict)
    source: Path | None = None


# Add new config items here first. This registry is the single source for
# defaults, TOML shape, CLI binding, parsing, and future mutability/scope data.
CONFIG_KEYS: tuple[ConfigKey, ...] = (
    # SLIDESHOW
    ConfigKey(
        "slideshow",
        "mode",
        None,
        parse_mode,
        argparse_entries=entries(
            "-m-",
            "mode",
            metavar="MODE",
            help="Mode string, for example B12W3",
        ),
        scope="both",
    ),
    ConfigKey(
        "slideshow",
        "provider",
        "weighted",
        parse_provider,
        argparse_entries=(
            ArgparseEntry(
                ("--provider",),
                metavar="PROVIDER",
                help="Initial image provider: weighted, CRW, burst, or random",
            ),
            ArgparseEntry(
                ("--random",),
                action="store_const",
                const="random",
                help="Start with the random image provider",
            ),
        ),
        choices=("weighted", "controlled_random_weighted", "burst", "random"),
        scope="both",
    ),
    ConfigKey(
        "slideshow",
        "video",
        True,
        parse_bool,
        argparse_entries=(
            ArgparseEntry(("--video",), action="store_true", help="Enable video playback"),
            ArgparseEntry(("--no-video", "--nv"), action="store_false", help="Disable video playback"),
        ),
        scope="both",
    ),
    ConfigKey(
        "slideshow",
        "mute",
        True,
        parse_bool,
        argparse_entries=entries(
            "no-mute",
            "nm",
            action="store_false",
            help="Disable mute",
        ),
        scope="both",
    ),
    ConfigKey(
        "slideshow",
        "navigation_basis",
        "folder",
        parse_choice("folder", "branch"),
        argparse_entries=entries(
            "navigation-basis",
            "nb",
            help="Default navigation basis: 'folder' or 'branch'",
        ),
        choices=("folder", "branch"),
        scope="runtime",
    ),
    ConfigKey(
        "slideshow",
        "interval",
        10000,
        parse_positive_int,
        argparse_entries=entries(
            "interval",
            metavar="INTERVAL",
            help="Time in milliseconds for automated slide changes",
        ),
        scope="both",
    ),
    ConfigKey(
        "slideshow",
        "auto",
        False,
        parse_bool,
        argparse_entries=(
            ArgparseEntry(
                ("--auto", "-a"),
                action=AutoAdvanceAction,
                nargs="?",
                metavar="INTERVAL",
                help=(
                    "Start automatic slide changes, optionally with interval "
                    "in milliseconds"
                ),
            ),
        ),
        scope="both",
    ),
    # PROGRESS
    ConfigKey(
        "progress",
        "quiet",
        False,
        parse_bool,
        argparse_entries=entries(
            "quiet",
            "-q",
            action="store_true",
            help="Suppress progress bars and progress toasts",
        ),
        scope="both",
    ),
    # CACHE
    ConfigKey(
        "cache",
        "background_preload",
        True,
        parse_bool,
        argparse_entries=(
            ArgparseEntry(
                ("--background-preload",),
                action="store_true",
                help="Enable background cache/preload refill",
            ),
            ArgparseEntry(
                ("--no-background", "--nbg"),
                action="store_false",
                help="Disable background cache/preload refill",
            ),
        ),
        scope="runtime",
    ),
    ConfigKey(
        "cache",
        "policy",
        "cache-all",
        parse_choice("cache-all", "bounded-bytes"),
        choices=("cache-all", "bounded-bytes"),
        scope="runtime",
    ),
    ConfigKey(
        "cache",
        "max_bytes",
        100 * 1024 * 1024,
        parse_positive_int,
        scope="runtime",
    ),
    ConfigKey(
        "cache",
        "preload_queue_length",
        3,
        parse_positive_int,
        scope="runtime",
    ),
    ConfigKey(
        "cache",
        "cache_size",
        10,
        parse_positive_int,
        scope="runtime",
    ),
    ConfigKey(
        "cache",
        "history_queue_length",
        25,
        parse_positive_int,
        scope="runtime",
    ),
)

CONFIG_KEYS_BY_NAME: dict[str, ConfigKey] = {key.name: key for key in CONFIG_KEYS}
CONFIG_KEY_NAMES: frozenset[str] = frozenset(CONFIG_KEYS_BY_NAME)
TOML_TABLE_NAMES: frozenset[str] = frozenset(key.toml_table for key in CONFIG_KEYS)
CONFIG_KEYS_BY_TOML_TABLE: dict[str, tuple[ConfigKey, ...]] = {
    table: tuple(key for key in CONFIG_KEYS if key.toml_table == table)
    for table in sorted(TOML_TABLE_NAMES)
}

_current_config: "Config | None" = None


def _require_config_key(key: str) -> ConfigKey:
    config_key = CONFIG_KEYS_BY_NAME.get(key)
    if config_key is None:
        raise KeyError(f"Unknown config key: {key}")
    return config_key


class Config:
    """Effective configuration facade for persisted, CLI, and runtime layers."""

    def __init__(
        self,
        app_config: AppConfig | None = None,
        args: Namespace | SimpleNamespace | None = None,
    ) -> None:
        self.app_config = app_config or AppConfig()
        self.args = args

    @classmethod
    def from_args(
        cls,
        args: Namespace | SimpleNamespace,
        *,
        start_folder: Path | None = None,
    ) -> "Config":
        app_config = load_app_config(getattr(args, "config", None), start_folder=start_folder)
        config = cls(app_config=app_config, args=args)
        global _current_config
        _current_config = config
        return config

    def __call__(self, key: str) -> Any:
        config_key = _require_config_key(key)
        cli_value = self._cli_value(config_key)
        if cli_value is not None:
            return cli_value
        app_value = self.app_config.values.get(key)
        if app_value is not None:
            return app_value
        return config_key.default

    def is_cli_override(self, key: str) -> bool:
        config_key = _require_config_key(key)
        return self._cli_value(config_key) is not None

    def _cli_value(self, config_key: ConfigKey) -> Any:
        if self.args is None or not config_key.argparse_entries:
            return None
        raw_value = getattr(self.args, config_key.name, None)
        if raw_value is None:
            return None
        return config_key.parser(raw_value)


def add_config_arguments(parser: argparse.ArgumentParser) -> None:
    for config_key in CONFIG_KEYS:
        if not config_key.argparse_entries:
            continue
        parser.set_defaults(**{config_key.name: None})
        for entry in config_key.argparse_entries:
            kwargs: dict[str, Any] = {
                "dest": entry.dest or config_key.name,
                "default": None,
            }
            if entry.help is not None:
                kwargs["help"] = entry.help
            if entry.action is not None:
                kwargs["action"] = entry.action
            else:
                kwargs["type"] = _argparse_type(config_key)
                if entry.metavar is not None:
                    kwargs["metavar"] = entry.metavar
                choices = entry.choices or config_key.choices
                if choices:
                    kwargs["choices"] = choices
            if entry.nargs is not None:
                kwargs["nargs"] = entry.nargs
            if entry.const is not None:
                kwargs["const"] = entry.const
            parser.add_argument(*entry.flags, **kwargs)


def _argparse_type(config_key: ConfigKey) -> Callable[[str], Any]:
    def parser(value: str) -> Any:
        parsed = config_key.parser(value)
        if parsed is None:
            raise argparse.ArgumentTypeError(
                f"invalid {config_key.name} value: {value!r}"
            )
        return parsed

    return parser


def get_current_config() -> Config:
    return _current_config if _current_config is not None else Config()


def discover_config_path(start_folder: Path | None = None) -> Path | None:
    """
    Search for enkan.toml in order: start folder -> user config -> app folder.

    Discovery order:
      1. start_folder (defaults to CWD if not supplied)
      2. %APPDATA%\\enkan on Windows; ~/.config/enkan on non-Windows / APPDATA unset
      3. The enkan package directory (directory containing this file)

    Returns the resolved path of the first match, or None if no file is found.
    This function is the single source of truth for config discovery behavior.
    """
    search_dirs: list[Path] = []

    search_dirs.append((start_folder or Path.cwd()).resolve())

    appdata = os.environ.get("APPDATA")
    if appdata:
        search_dirs.append(Path(appdata) / "enkan")
    else:
        search_dirs.append(Path.home() / ".config" / "enkan")

    search_dirs.append(Path(__file__).resolve().parent)

    for directory in search_dirs:
        candidate = directory / DEFAULT_CONFIG_FILENAME
        if candidate.is_file():
            return candidate.resolve()

    return None


def resolve_config_path(config_path: str | None = None, start_folder: Path | None = None) -> Path | None:
    """
    Return the config path to use.

    If config_path is given (explicit --config), resolve and return it directly;
    discovery is skipped entirely. If the explicit path does not exist, callers
    must raise ConfigError; this function returns the path without validating it.
    """
    if config_path:
        return Path(config_path).expanduser().resolve()

    return discover_config_path(start_folder=start_folder)


def load_app_config(config_path: str | None = None, start_folder: Path | None = None) -> AppConfig:
    path = resolve_config_path(config_path, start_folder=start_folder)
    if path is None:
        return AppConfig()
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    return _parse_app_config(raw, source=path)


def _parse_app_config(raw: dict[str, Any], *, source: Path) -> AppConfig:
    _require_table(raw, source=source, label="root")
    _reject_unknown_keys(raw, TOML_TABLE_NAMES, source=source, label="root")

    values: dict[str, Any] = {}
    for table_name, table_keys in CONFIG_KEYS_BY_TOML_TABLE.items():
        table = _optional_table(raw.get(table_name, {}))
        _reject_unknown_keys(
            table,
            {key.toml_key for key in table_keys},
            source=source,
            label=table_name,
        )
        for config_key in table_keys:
            if config_key.toml_key not in table:
                continue
            parsed = config_key.parser(table[config_key.toml_key])
            if parsed is not None:
                values[config_key.name] = parsed
            elif not config_key.invalid_fallback:
                raise ConfigError(
                    f"Invalid {table_name}.{config_key.toml_key} in {source}."
                )

    return AppConfig(values=values, source=source)


def _require_table(raw: Any, *, source: Path, label: str) -> None:
    if not isinstance(raw, dict):
        raise ConfigError(f"Invalid {label} table in {source}: expected TOML table.")


def _optional_table(raw: Any) -> dict[str, Any]:
    return raw if isinstance(raw, dict) else {}


def _reject_unknown_keys(
    raw: dict[str, Any], allowed: set[str] | frozenset[str], *, source: Path, label: str
) -> None:
    unknown = sorted(set(raw.keys()) - set(allowed))
    if unknown:
        formatted = ", ".join(unknown)
        raise ConfigError(f"Unknown {label} key(s) in {source}: {formatted}")
