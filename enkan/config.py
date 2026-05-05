from __future__ import annotations

import os
from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal
import tomllib

from enkan.constants import CX_PATTERN

DEFAULT_CONFIG_FILENAME = "enkan.toml"
VIDEO_CACHE_POLICIES = {"cache-all", "bounded-bytes"}
NAVIGATION_BASIS_VALUES = {"folder", "branch"}


class ConfigError(ValueError):
    """Raised when persisted configuration cannot be loaded or validated."""


@dataclass(frozen=True)
class VideoCacheConfig:
    policy: Literal["cache-all", "bounded-bytes"] | None = None
    max_bytes: int | None = None


@dataclass(frozen=True)
class AppConfig:
    mode: str | None = None
    random: bool | None = None
    dont_recurse: bool | None = None
    video: bool | None = None
    mute: bool | None = None
    quiet: bool | None = None
    no_background: bool | None = None
    navigation_basis: Literal["folder", "branch"] | None = None
    video_cache: VideoCacheConfig = field(default_factory=VideoCacheConfig)


BUILTIN_DEFAULTS: dict[str, Any] = {
    "mode": None,
    "random": False,
    "dont_recurse": False,
    "video": True,
    "mute": True,
    "quiet": False,
    "no_background": False,
    "navigation_basis": "folder",
    "video_cache.policy": "cache-all",
    "video_cache.max_bytes": 100 * 1024 * 1024,
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
        if key not in BUILTIN_DEFAULTS:
            raise KeyError(f"Unknown config key: {key}")
        if key in self.runtime_overrides:
            return self.runtime_overrides[key]
        cli_value = self._cli_value(key)
        if cli_value is not None:
            return cli_value
        app_value = self._app_value(key)
        if app_value is not None:
            return app_value
        return BUILTIN_DEFAULTS[key]

    def with_runtime_overrides(self, **overrides: Any) -> "Config":
        merged = {**self.runtime_overrides, **overrides}
        return Config(self.app_config, self.args, merged)

    def _cli_value(self, key: str) -> Any:
        if self.args is None or "." in key:
            return None
        return getattr(self.args, key, None)

    def _app_value(self, key: str) -> Any:
        if key == "video_cache.policy":
            return self.app_config.video_cache.policy
        if key == "video_cache.max_bytes":
            return self.app_config.video_cache.max_bytes
        return getattr(self.app_config, key)


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

    # 1. Start folder (project-local override)
    search_dirs.append((start_folder or Path.cwd()).resolve())

    # 2. User config folder
    appdata = os.environ.get("APPDATA")
    if appdata:
        search_dirs.append(Path(appdata) / "enkan")
    else:
        search_dirs.append(Path.home() / ".config" / "enkan")

    # 3. App folder (enkan package directory — same directory as this file)
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
    discovery is skipped entirely.  If the explicit path does not exist, callers
    must raise ConfigError — this function returns the path without validating it.

    Otherwise delegate to discover_config_path() using the discovery contract.
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
    _reject_unknown_keys(raw, {"slideshow", "video_cache"}, source=source, label="root")

    slideshow = _optional_table(raw.get("slideshow", {}))
    _reject_unknown_keys(
        slideshow,
        {"mode", "random", "dont_recurse", "video", "mute", "quiet", "no_background", "navigation_basis"},
        source=source,
        label="slideshow",
    )

    video_cache = _optional_table(raw.get("video_cache", {}))
    _reject_unknown_keys(
        video_cache,
        {"policy", "max_bytes"},
        source=source,
        label="video_cache",
    )

    mode = slideshow.get("mode")
    if mode is not None:
        mode = mode.lower() if isinstance(mode, str) and CX_PATTERN.fullmatch(mode) else None

    navigation_basis = slideshow.get("navigation_basis")
    if navigation_basis is not None:
        if not isinstance(navigation_basis, str) or navigation_basis not in NAVIGATION_BASIS_VALUES:
            navigation_basis = None

    return AppConfig(
        mode=mode,
        random=_optional_bool(slideshow, "random", source=source, label="slideshow"),
        dont_recurse=_optional_bool(slideshow, "dont_recurse", source=source, label="slideshow"),
        video=_optional_bool(slideshow, "video", source=source, label="slideshow"),
        mute=_optional_bool(slideshow, "mute", source=source, label="slideshow"),
        quiet=_optional_bool(slideshow, "quiet", source=source, label="slideshow"),
        no_background=_optional_bool(slideshow, "no_background", source=source, label="slideshow"),
        navigation_basis=navigation_basis,
        video_cache=VideoCacheConfig(
            policy=_video_cache_policy(video_cache, source=source),
            max_bytes=_video_cache_max_bytes(video_cache, source=source),
        ),
    )


def _require_table(raw: Any, *, source: Path, label: str) -> None:
    if not isinstance(raw, dict):
        raise ConfigError(f"Invalid {label} table in {source}: expected TOML table.")


def _optional_table(raw: Any) -> dict[str, Any]:
    return raw if isinstance(raw, dict) else {}


def _reject_unknown_keys(
    raw: dict[str, Any], allowed: set[str], *, source: Path, label: str
) -> None:
    unknown = sorted(set(raw.keys()) - allowed)
    if unknown:
        formatted = ", ".join(unknown)
        raise ConfigError(f"Unknown {label} key(s) in {source}: {formatted}")


def _optional_bool(
    raw: dict[str, Any], key: str, *, source: Path, label: str
) -> bool | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        return None
    return value


def _video_cache_policy(raw: dict[str, Any], *, source: Path) -> str | None:
    value = raw.get("policy")
    if value is None:
        return None
    if not isinstance(value, str) or value not in VIDEO_CACHE_POLICIES:
        return None
    return value


def _video_cache_max_bytes(raw: dict[str, Any], *, source: Path) -> int | None:
    value = raw.get("max_bytes")
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return None
    return value
