from __future__ import annotations
import copy
import re
from typing import Dict, List, Tuple, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from enkan.config import Config

# Mode type: level -> (mode_char, [slope1, slope2])
ModeMap = Dict[int, Tuple[str, List[int]]]

_current_defaults: Defaults | None = None


def set_current_defaults(defaults: "Defaults") -> None:
    global _current_defaults
    _current_defaults = defaults


def get_current_defaults() -> "Defaults":
    return _current_defaults if _current_defaults is not None else Defaults()


class Defaults:
    """
    Holds global / CLI overrides and mutable runtime defaults.
    Resolution order for each property:
    CLI args override > global_* override > initial value passed at construction.
    """

    def __init__(
        self,
        weight_modifier: int = 100,
        mode: Any | None = None,
        dont_recurse: bool = False,
        args: Any | None = None,
        video: bool = True,
        config: "Config | None" = None,
    ):
        self.args = args
        self.config = config

        if config is not None:
            if mode is None:
                mode = config("slideshow.mode")
            dont_recurse = bool(config("slideshow.dont_recurse"))
            video = bool(config("slideshow.video"))

        # Base values
        self._weight_modifier = weight_modifier
        self._mode: ModeMap = _ensure_mode_map(mode)
        self._dont_recurse: bool = dont_recurse
        self._video: bool = video

        # CLI-sourced overrides (stored separately so properties can resolve precedence)
        self.args_mode: ModeMap | None = (
            _ensure_mode_map(args.mode)
            if args and getattr(args, "mode", None) is not None
            else None
        )
        self.args_dont_recurse = getattr(args, "dont_recurse", None) if args else None
        self.args_video = getattr(args, "video", None) if args else None

        # Global (runtime) overrides (set later via setters)
        self.global_mode: ModeMap | None = None
        self.global_dont_recurse: bool | None = None
        self.global_video: bool | None = None

        # Group metadata container
        self.groups: dict[str, Any] = {}

    def clone_for_source(self) -> "Defaults":
        """
        Create a source-local clone for input parsing/building.

        This preserves current CLI override precedence and any already-resolved
        top-level runtime defaults, while isolating per-source mutations such as
        txt-file globals and group definitions from the shared runtime Defaults.
        """
        clone = Defaults(
            weight_modifier=self._weight_modifier,
            mode=_copy_mode_map(self._mode),
            dont_recurse=self._dont_recurse,
            args=self.args,
            video=self._video,
            config=self.config,
        )
        clone.global_mode = _copy_mode_map(self.global_mode)
        clone.global_dont_recurse = self.global_dont_recurse
        clone.global_video = self.global_video
        clone.groups = copy.deepcopy(self.groups)
        return clone

    @property
    def weight_modifier(self) -> int:
        return self._weight_modifier

    @property
    def mode(self) -> ModeMap:
        if self.args_mode is not None:
            return self.args_mode
        if self.global_mode is not None:
            return self.global_mode
        return self._mode

    @property
    def dont_recurse(self) -> bool:
        if self.args_dont_recurse is not None:
            return self.args_dont_recurse
        if self.global_dont_recurse is not None:
            return self.global_dont_recurse
        return self._dont_recurse

    @property
    def video(self) -> bool:
        if self.args_video is not None:
            return self.args_video
        if self.global_video is not None:
            return self.global_video
        return self._video

    def set_global_defaults(
        self,
        mode: Any | None = None,
        dont_recurse: bool | None = None,
    ) -> None:
        if mode is not None:
            self.global_mode = _ensure_mode_map(mode)
        if dont_recurse is not None:
            self.global_dont_recurse = dont_recurse

    def set_global_video(self, video: bool | None = None) -> None:
        if video is not None:
            self.global_video = video


class Mode:
    """Wrapper around a ModeMap providing parsing and resolution."""

    def __init__(self, mode_map: Optional[ModeMap] = None) -> None:
        self.map: ModeMap = mode_map or {}

    @classmethod
    def from_string(cls, mode_str: str) -> "Mode":
        return cls(parse_mode_string(mode_str))

    def resolve(self, level: int) -> Tuple[str, List[int]]:
        return resolve_mode(self.map, level)

    def serialise(self) -> Optional[str]:
        return serialise_mode(self.map)

    def __bool__(self) -> bool:
        return bool(self.map)

    def __repr__(self) -> str:
        return f"Mode({self.serialise()!r})"


def _ensure_mode_map(mode: Any) -> ModeMap:
    if mode is None:
        return {1: ("w", [0, 0])}
    if isinstance(mode, dict):
        out: ModeMap = {}
        for level, val in mode.items():
            if isinstance(val, tuple):
                ch, slopes = val
                slopes_list = list(slopes or [])
                if len(slopes_list) < 2:
                    slopes_list.extend([0] * (2 - len(slopes_list)))
                out[int(level)] = (str(ch), slopes_list[:2])
            else:
                out[int(level)] = (str(val), [0, 0])
        return out
    if isinstance(mode, str):
        return parse_mode_string(mode)
    raise TypeError(f"Unsupported mode type: {type(mode).__name__}")


def _copy_mode_map(mode_data: Optional[ModeMap]) -> Optional[ModeMap]:
    if mode_data is None:
        return None
    return {
        int(level): (str(ch), list(slopes or []))
        for level, (ch, slopes) in mode_data.items()
    }


def parse_mode_string(mode_str: str) -> ModeMap:
    pattern = re.compile(r"([bw])(\d+)(?:,(-?\d+))?(?:,(-?\d+))?", re.IGNORECASE)
    matches = pattern.findall(mode_str)
    result: ModeMap = {}
    for char, num, slope1, slope2 in matches:
        level = int(num)
        s1 = int(slope1) if slope1 else 0
        s2 = int(slope2) if slope2 else 0
        result[level] = (char.lower(), [s1, s2])
    return result


def serialise_mode(mode_data: Optional[ModeMap]) -> Optional[str]:
    if not mode_data:
        return None
    parts: List[str] = []
    for level in sorted(mode_data.keys()):
        ch, slopes = mode_data[level]
        s = list(slopes or [])
        if len(s) < 2:
            s.extend([0] * (2 - len(s)))
        parts.append(f"{ch}{level},{s[0]},{s[1]}")
    return " ".join(parts)


def resolve_mode(mode_dict: ModeMap, number: int) -> Tuple[str, List[int]]:
    if not mode_dict:
        return ("w", [0, 0])
    first_key = min(mode_dict.keys())
    if number < first_key:
        return ("l", [0, 0])  # Sentinel for levels above the first configured rung.
    if number in mode_dict:
        ch, slopes = mode_dict[number]
        s = list(slopes or [])
        if len(s) < 2:
            s.extend([0] * (2 - len(s)))
        return ch, s[:2]
    return ("w", [0, 0])
