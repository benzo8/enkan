from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from enkan.utils.Defaults import ModeMap
from enkan.tree.tree_logic import Tree


class SourceKind(str, Enum):
    TXT = "txt"
    LST = "lst"
    TREE = "tree"
    FOLDER = "folder"


@dataclass
class LoadedSource:
    """
    Normalised representation of a single input before merging.

    tree:
        Populated when reconstructed (lst/txt) or loaded (.tree).
    """

    source_path: str
    kind: SourceKind
    order_index: int
    tree: Optional["Tree"] = None
    mode: ModeMap | None = None
    mode_string: str | None = None
    lowest_rung: int | None = None
    graft_offset: int | None = None
    provenance: str | None = None
    warnings: List[str] = field(default_factory=list)


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
    # Heuristic: treat everything else as a folder/path-like input and let the
    # caller refine validity later.
    return SourceKind.FOLDER
