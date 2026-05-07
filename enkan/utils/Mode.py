from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

ModeMap = Dict[int, Tuple[str, List[int]]]


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


def ensure_mode_map(mode: Any) -> ModeMap:
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


def copy_mode_map(mode_data: Optional[ModeMap]) -> Optional[ModeMap]:
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
        return ("l", [0, 0])
    if number in mode_dict:
        ch, slopes = mode_dict[number]
        s = list(slopes or [])
        if len(s) < 2:
            s.extend([0] * (2 - len(s)))
        return ch, s[:2]
    return ("w", [0, 0])
