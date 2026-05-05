from __future__ import annotations

import os
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
CliTransform = Callable[[Any], Any]


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


def parse_positive_int(value: Any) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return None
    return value


def invert_bool(value: Any) -> Any:
    return not value if isinstance(value, bool) else value


@dataclass(frozen=True)
class ConfigKey:
    name: str
    toml_table: str
    toml_key: str
    default: Any
    parser: ConfigParser
    cli_dest: str | None = None
    cli_transform: CliTransform | None = None
    choices: tuple[str, ...] = ()
    scope: ConfigScope = "both"
    invalid_fallback: bool = True


@dataclass(frozen=True)
class AppConfig:
    values: dict[str, Any] = field(default_factory=dict)
    source: Path | None = None


# Add new config items here first. This registry is the single source for
# defaults, TOML shape, CLI binding, parsing, and future mutability/scope data.
CONFIG_KEYS: tuple[ConfigKey, ...] = (
    ConfigKey("mode", "slideshow", "mode", None, parse_mode, cli_dest="mode", scope="both"),
    ConfigKey("random", "slideshow", "random", False, parse_bool, cli_dest="random", scope="both"),
    ConfigKey("dont_recurse", "slideshow", "dont_recurse", False, parse_bool, cli_dest="dont_recurse", scope="both"),
    ConfigKey("video", "slideshow", "video", True, parse_bool, cli_dest="video", scope="both"),
    ConfigKey("mute", "slideshow", "mute", True, parse_bool, cli_dest="mute", scope="both"),
    ConfigKey("progress.quiet", "progress", "quiet", False, parse_bool, cli_dest="quiet", scope="both"),
    ConfigKey(
        "navigation_basis",
        "slideshow",
        "navigation_basis",
        "folder",
        parse_choice("folder", "branch"),
        cli_dest="navigation_basis",
        choices=("folder", "branch"),
        scope="runtime",
    ),
    ConfigKey(
        "cache.background_preload",
        "cache",
        "background_preload",
        True,
        parse_bool,
        cli_dest="no_background",
        cli_transform=invert_bool,
        scope="runtime",
    ),
    ConfigKey(
        "cache.policy",
        "cache",
        "policy",
        "cache-all",
        parse_choice("cache-all", "bounded-bytes"),
        choices=("cache-all", "bounded-bytes"),
        scope="runtime",
    ),
    ConfigKey(
        "cache.max_bytes",
        "cache",
        "max_bytes",
        100 * 1024 * 1024,
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


class Config:
    """Effective configuration facade for persisted, CLI, and runtime layers."""

    def __init__(
        self,
        app_config: AppConfig | None = None,
        args: Namespace | SimpleNamespace | None = None,
        runtime_overrides: dict[str, Any] | None = None,
    ) -> None:
        self.app_config = app_config or AppConfig()
        self.args = args
        self.runtime_overrides: dict[str, Any] = dict(runtime_overrides or {})

    @classmethod
    def from_args(
        cls,
        args: Namespace | SimpleNamespace,
        *,
        start_folder: Path | None = None,
    ) -> "Config":
        app_config = load_app_config(getattr(args, "config", None), start_folder=start_folder)
        return cls(app_config=app_config, args=args)

    def __call__(self, key: str) -> Any:
        config_key = CONFIG_KEYS_BY_NAME.get(key)
        if config_key is None:
            raise KeyError(f"Unknown config key: {key}")
        if key in self.runtime_overrides:
            return self.runtime_overrides[key]
        cli_value = self._cli_value(config_key)
        if cli_value is not None:
            return cli_value
        app_value = self.app_config.values.get(key)
        if app_value is not None:
            return app_value
        return config_key.default

    def with_runtime_overrides(self, **overrides: Any) -> "Config":
        merged = {**self.runtime_overrides, **overrides}
        return Config(self.app_config, self.args, merged)

    def _cli_value(self, config_key: ConfigKey) -> Any:
        if self.args is None or config_key.cli_dest is None:
            return None
        raw_value = getattr(self.args, config_key.cli_dest, None)
        if raw_value is None:
            return None
        if config_key.cli_transform is not None:
            raw_value = config_key.cli_transform(raw_value)
        return config_key.parser(raw_value)


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
