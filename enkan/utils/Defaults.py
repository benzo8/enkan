import re


from typing import Dict, List, Tuple, Optional, Any

# Mode type used throughout: level -> (mode_char, [slope1, slope2])
ModeMap = Dict[int, Tuple[str, List[int]]]

class Defaults:
    def __init__(
        self,
        weight_modifier=100,
        mode=None,
        is_random=False,
        dont_recurse=False,
        args=None,
        video=True,
        mute=True,
    ):
        self.args = args
        self._weight_modifier = weight_modifier
        self._mode: ModeMap = _ensure_mode_map(mode)
        self._is_random: bool = is_random
        self._dont_recurse: bool = dont_recurse
        self._video: bool = video
        self._mute: bool = mute

        self.global_mode = None
        self.global_is_random = None
        self.global_dont_recurse = None
        self.global_video = None
        self.global_mute = None

        self.args_mode: ModeMap | None = (
            _ensure_mode_map(args.mode) if args and args.mode is not None else None
        )
        self.args_is_random = args.random if args and args.random is not None else None
        self.args_dont_recurse = (
            args.dont_recurse if args and args.dont_recurse is not None else None
        )
        self.args_video = args.video if args and args.video is not None else None
        self.args_mute = args.mute if args and args.mute is not None else None

        self.debug = args.debug
        self.background: bool = not args.no_background

        self.groups = {}

    @property
    def weight_modifier(self) -> int:
        return self._weight_modifier

    @property
    def mode(self) -> ModeMap:
        if self.args_mode is not None:
            return self.args_mode
        elif self.global_mode is not None:
            return self.global_mode
        else:
            return self._mode

    @property
    def is_random(self):
        if self.args_is_random is not None:
            return self.args_is_random
        elif self.global_is_random is not None:
            return self.global_is_random
        else:
            return self._is_random

    @property
    def dont_recurse(self):
        if self.args_dont_recurse is not None:
            return self.args_dont_recurse
        elif self.global_dont_recurse is not None:
            return self.global_dont_recurse
        else:
            return self._dont_recurse

    @property
    def video(self):
        if self.args_video is not None:  # CLI overrides all
            return self.args_video
        elif self.global_video is not None:  # folder-specific config
            return self.global_video
        else:
            return self._video  # built-in fallback

    @property
    def mute(self):
        if self.args_mute is not None:
            return self.args_mute
        elif self.global_mute is not None:
            return self.global_mute
        else:
            return self._mute

    def set_global_defaults(self, mode=None, is_random=None, dont_recurse=None) -> None:
        if mode is not None:
            self.global_mode: ModeMap = _ensure_mode_map(mode)
        if is_random is not None:
            self.global_is_random = is_random
        if dont_recurse is not None:
            self.global_dont_recurse = dont_recurse

    def set_global_video(self, video=None, mute=None) -> None:
        if video is not None:
            self.global_video = video
        if mute is not None:
            self.global_mute = mute


class Mode:
    """
    Lightweight wrapper around ModeMap to keep mode parsing/serialising/resolution in one place.
    """

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
    """
    Normalise various mode representations to ModeMap.
    Supports legacy dicts with string values.
    """
    if mode is None:
        return {1: ("w", [0, 0])}
    if isinstance(mode, dict):
        normalised: ModeMap = {}
        for level, val in mode.items():
            if isinstance(val, tuple):
                mode_char, slopes = val
                slopes_list: List[int] = list(slopes or [])
                if len(slopes_list) < 2:
                    slopes_list.extend([0] * (2 - len(slopes_list)))
                normalised[int(level)] = (str(mode_char), slopes_list[:2])
            else:
                normalised[int(level)] = (str(val), [0, 0])
        return normalised
    # Fallback: parse from string if mode is a string, else raise TypeError
    if isinstance(mode, str):
        return parse_mode_string(mode)
    raise TypeError(
        f"_ensure_mode_map: Unsupported type for mode: {type(mode).__name__}. "
        "Expected None, dict, or str."
    )
def parse_mode_string(mode_str: str) -> ModeMap:
    # Updated regex: ([bw])(\d+)(?:,(-?\d+))?(?:,(-?\d+))?
    pattern = re.compile(r"([bw])(\d+)(?:,(-?\d+))?(?:,(-?\d+))?", re.IGNORECASE)
    matches = pattern.findall(mode_str)
    # Each match is a tuple: (mode, level, slope1, slope2)
    # Convert level to int, slopes to int if present, else None
    result: ModeMap = {}
    for char, num, slope1, slope2 in matches:
        level = int(num)
        slopes: List[int] = []
        if slope1:
            slopes.append(int(slope1))
        else:
            slopes.append(0)
        if slope2:
            slopes.append(int(slope2))
        else:
            slopes.append(0)
        result[level] = (char.lower(), slopes)
    return result


def serialise_mode(mode_data: Optional[ModeMap]) -> Optional[str]:
    """
    Convert ModeMap to a string for display/export.
    """
    if not mode_data:
        return None

    parts: List[str] = []
    for level in sorted(mode_data.keys()):
        info = mode_data[level]
        if isinstance(info, tuple):
            mode_char, slopes = info
            slopes_list: List[int] = list(slopes or [])
            if len(slopes_list) < 2:
                slopes_list.extend([0] * (2 - len(slopes_list)))
            part = f"{mode_char}{level}"
            part += "," + ",".join(str(int(s)) for s in slopes_list[:2])
            parts.append(part)
        else:
            parts.append(f"{info}{level}")
    return " ".join(parts)


def resolve_mode(mode_dict: ModeMap, number: int) -> Tuple[str, List[int]]:
    """
    Resolve the mode and slopes that apply at a given level.
    Falls back to weighted with zero slope when undefined.
    """
    if not mode_dict:
        return ("w", [0, 0])

    first_key = min(mode_dict.keys())

    if number < first_key:
        return ("l", [0, 0])
    if number in mode_dict:
        mode_char, slopes = mode_dict[number]
        slopes_list: List[int] = list(slopes or [])
        if len(slopes_list) < 2:
            slopes_list.extend([0] * (2 - len(slopes_list)))
        return mode_char, slopes_list[:2]

    return ("w", [0, 0])
