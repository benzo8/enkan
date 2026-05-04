from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal
import tomllib

from enkan.constants import CX_PATTERN

DEFAULT_CONFIG_FILENAME = "enkan.toml"
VIDEO_CACHE_POLICIES = {"cache-all", "bounded-bytes"}


class ConfigError(ValueError):
    """Raised when persisted configuration cannot be loaded or validated."""


@dataclass(frozen=True)
class VideoCacheConfig:
    policy: Literal["cache-all", "bounded-bytes"] = "cache-all"
    max_bytes: int = 100 * 1024 * 1024


@dataclass(frozen=True)
class AppConfig:
    mode: str | None = None
    random: bool | None = None
    dont_recurse: bool | None = None
    video: bool | None = None
    mute: bool | None = None
    quiet: bool | None = None
    no_background: bool | None = None
    video_cache: VideoCacheConfig = field(default_factory=VideoCacheConfig)


_current_app_config: AppConfig | None = None


def set_current_app_config(config: AppConfig | None) -> None:
    global _current_app_config
    _current_app_config = config


def get_current_app_config() -> AppConfig:
    return _current_app_config if _current_app_config is not None else AppConfig()


def resolve_config_path(config_path: str | None = None) -> Path | None:
    if config_path:
        return Path(config_path).expanduser().resolve()

    candidate = Path.cwd() / DEFAULT_CONFIG_FILENAME
    if candidate.is_file():
        return candidate.resolve()
    return None


def load_app_config(config_path: str | None = None) -> AppConfig:
    path = resolve_config_path(config_path)
    if path is None:
        return AppConfig()
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    return _parse_app_config(raw, source=path)


def merge_config_into_args(args: Namespace | SimpleNamespace, config: AppConfig):
    merged = SimpleNamespace(**vars(args))
    cli_overridable_fields = (
        "mode",
        "random",
        "dont_recurse",
        "video",
        "mute",
        "quiet",
        "no_background",
    )

    for field_name in cli_overridable_fields:
        if getattr(merged, field_name, None) is None:
            config_value = getattr(config, field_name)
            if config_value is not None:
                setattr(merged, field_name, config_value)

    return merged


def _parse_app_config(raw: dict[str, Any], *, source: Path) -> AppConfig:
    _require_table(raw, source=source, label="root")
    _reject_unknown_keys(raw, {"slideshow", "video_cache"}, source=source, label="root")

    slideshow = raw.get("slideshow", {})
    _require_table(slideshow, source=source, label="slideshow")
    _reject_unknown_keys(
        slideshow,
        {"mode", "random", "dont_recurse", "video", "mute", "quiet", "no_background"},
        source=source,
        label="slideshow",
    )

    video_cache = raw.get("video_cache", {})
    _require_table(video_cache, source=source, label="video_cache")
    _reject_unknown_keys(
        video_cache,
        {"policy", "max_bytes"},
        source=source,
        label="video_cache",
    )

    mode = slideshow.get("mode")
    if mode is not None:
        if not isinstance(mode, str) or not CX_PATTERN.fullmatch(mode):
            raise ConfigError(
                f"Invalid slideshow.mode in {source}: expected CX pattern string."
            )
        mode = mode.lower()

    return AppConfig(
        mode=mode,
        random=_optional_bool(slideshow, "random", source=source, label="slideshow"),
        dont_recurse=_optional_bool(slideshow, "dont_recurse", source=source, label="slideshow"),
        video=_optional_bool(slideshow, "video", source=source, label="slideshow"),
        mute=_optional_bool(slideshow, "mute", source=source, label="slideshow"),
        quiet=_optional_bool(slideshow, "quiet", source=source, label="slideshow"),
        no_background=_optional_bool(slideshow, "no_background", source=source, label="slideshow"),
        video_cache=VideoCacheConfig(
            policy=_video_cache_policy(video_cache, source=source),
            max_bytes=_video_cache_max_bytes(video_cache, source=source),
        ),
    )


def _require_table(raw: Any, *, source: Path, label: str) -> None:
    if not isinstance(raw, dict):
        raise ConfigError(f"Invalid {label} table in {source}: expected TOML table.")


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
        raise ConfigError(f"Invalid {label}.{key} in {source}: expected boolean.")
    return value


def _video_cache_policy(raw: dict[str, Any], *, source: Path) -> str:
    value = raw.get("policy", VideoCacheConfig().policy)
    if not isinstance(value, str) or value not in VIDEO_CACHE_POLICIES:
        allowed = ", ".join(sorted(VIDEO_CACHE_POLICIES))
        raise ConfigError(
            f"Invalid video_cache.policy in {source}: expected one of {allowed}."
        )
    return value


def _video_cache_max_bytes(raw: dict[str, Any], *, source: Path) -> int:
    value = raw.get("max_bytes", VideoCacheConfig().max_bytes)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(
            f"Invalid video_cache.max_bytes in {source}: expected positive integer."
        )
    return value