from __future__ import annotations

import os
from collections import defaultdict
from typing import List, Tuple

from enkan.tree.Tree import Tree
from enkan.tree.tree_logic import calculate_weights
from enkan.utils.Filters import Filters
from enkan.utils.Defaults import Defaults


def _parse_list_line(line: str) -> Tuple[str, float]:
    """
    Parse a single .lst line into (path, weight).
    Falls back to weight 1.0 when absent or invalid.
    """
    if not line or line.startswith("#"):
        return "", 0.0

    line = line.strip().strip('"')
    if "," not in line:
        return line, 1.0

    path, weight_str = line.rsplit(",", 1)
    path = path.strip().strip('"')
    weight_str = weight_str.strip()
    try:
        weight = float(weight_str)
    except ValueError:
        # Comma inside filename; treat whole line as path
        return line, 1.0
    return path, weight if weight > 0 else 1.0


def _normalise_proportions(entries: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
    total = sum(weight for _, weight in entries) or 1.0
    return [(path, (weight / total) * 100.0) for path, weight in entries]


def build_tree_from_list(
    list_path: str,
    defaults: Defaults,
    filters: Filters,
    quiet: bool = False,
) -> Tree:
    """
    Reconstruct a Tree from a .lst file to enable navigation and reweighting.
    Weighting is approximated by translating per-entry weights into sibling proportions.
    """
    tree = Tree(defaults, filters)
    grouped: dict[str, List[Tuple[str, float]]] = defaultdict(list)

    try:
        with open(list_path, "r", encoding="utf-8", buffering=65536) as f:
            for raw in f:
                path, weight = _parse_list_line(raw.strip())
                if not path:
                    continue
                dir_path = os.path.dirname(path) or "root"
                grouped[dir_path].append((path, weight))
    except OSError as exc:
        raise ValueError(f"Unable to read list file '{list_path}': {exc}") from exc

    for dir_path, items in grouped.items():
        weighted = _normalise_proportions(items)
        for path, proportion in weighted:
            node_name = os.path.join(
                os.path.dirname(path),
                os.path.splitext(os.path.basename(path))[0],
            )
            tree.create_node(
                node_name,
                {
                    "weight_modifier": 100,
                    "is_percentage": True,
                    "proportion": proportion,
                    "mode_modifier": None,
                    "images": [path],
                },
            )

    calculate_weights(tree)
    return tree
