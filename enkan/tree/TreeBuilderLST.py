from __future__ import annotations

import os
from collections import defaultdict
from typing import List, Tuple

from enkan.constants import ROOT_NODE_NAME
from enkan.tree.Tree import Tree
from tqdm import tqdm

"""
Builder for .lst list sources.
"""


class TreeBuilderLST:
    def __init__(self, tree: Tree) -> None:
        self.tree = tree

    def _parse_list_line(self, line: str) -> Tuple[str, float] | None:
        """
        Parse a single .lst line into (path, weight).
        Returns None for comments/blank lines.
        """
        if not line or line.startswith("#"):
            return None

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

    def build(self, list_path: str) -> None:
        """
        Reconstruct a Tree from a .lst file to enable navigation and reweighting.
        Groups images by containing folder; proportions are derived from summed weights.
        """
        grouped: dict[str, List[Tuple[str, float]]] = defaultdict(list)

        try:
            with open(list_path, "r", encoding="utf-8", buffering=65536) as f:
                total_lines = sum(1 for _ in f)
                f.seek(0)
                for raw in tqdm(
                    f,
                    desc=f"Parsing {list_path}",
                    leave=True,
                    unit="line",
                    total=total_lines or None,
                ):
                    parsed = self._parse_list_line(raw.strip())
                    if not parsed:
                        continue
                    path, weight = parsed
                    dir_path = os.path.dirname(path) or ROOT_NODE_NAME
                    grouped[dir_path].append((path, weight))
        except OSError as exc:
            raise ValueError(f"Unable to read list file '{list_path}': {exc}") from exc

        if not grouped:
            raise ValueError(f"No entries found in list file '{list_path}'.")

        dir_weights: dict[str, float] = {
            dir_path: sum(weight for _, weight in entries)
            for dir_path, entries in grouped.items()
        }
        total_weight = sum(dir_weights.values()) or len(dir_weights) or 1.0

        with tqdm(
            total=len(grouped),
            desc=f"Building nodes from {os.path.basename(list_path)}",
            leave=True,
            unit="dir",
        ) as pbar:
            for dir_path, entries in grouped.items():
                images = [path for path, _ in entries]
                proportion = (dir_weights[dir_path] / total_weight) * 100.0
                self.tree.create_node(
                    dir_path,
                    {
                        "weight_modifier": 100,
                        "is_percentage": True,
                        "proportion": proportion,
                        "mode_modifier": None,
                        "images": images,
                    },
                )
                pbar.update(1)
