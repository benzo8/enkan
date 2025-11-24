from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from enkan import constants
from enkan.utils.Defaults import ModeMap
from enkan.tree.tree_logic import Tree


class SourceKind(str, Enum):
    TXT = "txt"
    LST = "lst"
    TREE = "tree"
    FOLDER = "folder"
    OTHER = "other"


@dataclass
class LoadedSource:
    """
    Normalised representation of a single input before merging.

    tree:
        Populated when reconstructed (lst/txt) or loaded (.tree).
    globals:
        Captures global blocks (mode/video/mute/dont_recurse) parsed from txt.
    """

    source_path: str
    kind: SourceKind
    order_index: int
    tree: Optional["Tree"] = None
    globals: Optional[Dict[str, Any]] = None
    mode: ModeMap | None = None
    warnings: List[str] = field(default_factory=list)
    inferred: bool = False  # True for backfilled/reconstructed sources


def classify_input_path(path: str) -> SourceKind:
    """
    Lightweight classifier for an input path based on extension.
    """
    lower = path.lower()
    if lower.endswith(".txt"):
        return SourceKind.TXT
    if lower.endswith(".lst"):
        return SourceKind.LST
    if lower.endswith(".tree"):
        return SourceKind.TREE
    if not lower.endswith((".txt", ".lst", ".tree")):
        # Heuristic: treat as folder if it exists; caller can refine
        return SourceKind.FOLDER
    return SourceKind.OTHER


def _looks_like_nested_reference(line: str) -> bool:
    """
    Heuristic: does a txt line point to another input file?
    Strips modifiers before checking extension.
    """
    stripped = constants.MODIFIER_PATTERN.sub("", line).strip().strip('"')
    lower = stripped.lower()
    return lower.endswith((".txt", ".lst", ".tree"))


def _txt_contains_nested_inputs(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8", buffering=65536) as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if _looks_like_nested_reference(line):
                    return True
    except OSError:
        # If the file cannot be read, fall back to conservative merge path
        return True
    return False


def should_bypass_merge(inputs: Iterable[str]) -> bool:
    """
    Fast-path decision: skip merge when a single input can be handled directly.
    We still peek into a lone .txt to see if it pulls in other files.
    """
    inputs = list(inputs)
    if len(inputs) != 1:
        return False
    single = inputs[0]
    kind = classify_input_path(single)
    if kind == SourceKind.TXT:
        return not _txt_contains_nested_inputs(single)
    # .lst files need to be reconstructed into a tree even when alone
    if kind == SourceKind.LST:
        return False
    return kind in {SourceKind.TREE, SourceKind.FOLDER}
