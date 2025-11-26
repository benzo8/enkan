from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

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
    mode_string: str | None = None
    lowest_rung: int | None = None
    graft_offset: int | None = None
    provenance: str | None = None
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
