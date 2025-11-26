from __future__ import annotations

import os
import logging
from collections import defaultdict
from typing import Dict, List, Tuple

from enkan.constants import ROOT_NODE_NAME
from enkan.tree.Tree import Tree
from tqdm import tqdm
from enkan.utils.Defaults import serialise_mode

logger = logging.getLogger(__name__)

"""
Builder for .lst list sources.
"""



class TreeBuilderLST:
    def __init__(self, tree: Tree) -> None:
        self.tree = tree

    def _parse_list_line(self, line: str) -> Tuple[str, float, bool] | None:
        """
        Parse a single .lst line into (path, weight, had_explicit_weight).
        Returns None for comments/blank lines.
        """
        if not line or line.startswith("#"):
            return None

        line = line.strip().strip('"')
        if "," not in line:
            return line, 1.0, False

        path, weight_str = line.rsplit(",", 1)
        path = path.strip().strip('"')
        weight_str = weight_str.strip()
        try:
            weight = float(weight_str)
        except ValueError:
            # Comma inside filename; treat whole line as path
            return line, 1.0, False
        return path, (weight if weight > 0 else 1.0), True

    def build(self, list_path: str) -> None:
        """
        Reconstruct a Tree from a .lst file to enable navigation and reweighting.
        Groups images by containing folder; proportions are derived from summed weights.
        """
        grouped: dict[str, List[Tuple[str, float]]] = defaultdict(list)
        explicit_weights_found: bool = False

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
                    path, weight, had_weight = parsed
                    if had_weight:
                        explicit_weights_found = True
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
        # total_weight = sum(dir_weights.values()) or len(dir_weights) or 1.0

        with tqdm(
            total=len(grouped),
            desc=f"Building nodes from {os.path.basename(list_path)}",
            leave=True,
            unit="dir",
        ) as pbar:
            for dir_path, entries in grouped.items():
                images = [path for path, _ in entries]
                self.tree.create_node(
                    dir_path,
                    {
                        "weight_modifier": 100,
                        "is_percentage": True,
                        "proportion": None,
                        "mode_modifier": None,
                        "images": images,
                    },
                )
                node = self.tree.path_lookup.get(dir_path)
                if node:
                    node.weight = dir_weights[dir_path]
                pbar.update(1)
        # Record whether the source .lst had explicit weights for downstream inference
        setattr(self.tree, "lst_has_weights", explicit_weights_found)
        self._infer_mode_from_tree()

    def _infer_mode_from_tree(self) -> None:
        if not getattr(self.tree, "lst_has_weights", False):
            self.tree.lst_inferred_mode = None
            self.tree.lst_inferred_lowest = None
            self.tree.lst_inferred_warning = "List has no explicit weights; mode not harmonised."
            self.tree.built_mode = None
            self.tree.built_mode_string = None
            return

        level_weights: Dict[int, List[float]] = {}
        for node in self.tree.node_lookup.values():
            if node.name == ROOT_NODE_NAME:
                continue
            if getattr(node, "weight", None) is None:
                continue
            level_weights.setdefault(node.level, []).append(node.weight)

        if not level_weights:
            self.tree.lst_inferred_mode = None
            self.tree.lst_inferred_lowest = None
            self.tree.lst_inferred_warning = "No nodes found while inferring mode."
            self.tree.built_mode = None
            self.tree.built_mode_string = None
            return

        tolerance: float = 1e-6
        confidence_threshold: float = 80 / 100  # 80%
        for level in sorted(level_weights.keys()):
            weights = level_weights[level]
            if not weights:
                continue
            if max(weights) - min(weights) <= tolerance:
                self.tree.lst_inferred_mode = {level: ("b", (0, 0))}
                self.tree.built_mode = self.tree.lst_inferred_mode
                self.tree.built_mode_string = serialise_mode(self.tree.built_mode)
                self.tree.lst_inferred_lowest = level
                self.tree.lst_inferred_warning = None
                return
            # Cluster check: if a dominant cluster (>=90%) sits within tolerance, assume balanced
            best_cluster = 0
            for w in weights:
                cluster_size = sum(1 for v in weights if abs(v - w) <= tolerance)
                if cluster_size > best_cluster:
                    best_cluster = cluster_size
            confidence = best_cluster / len(weights)
            if confidence >= confidence_threshold:
                self.tree.lst_inferred_mode = {level: ("b", (0, 0))}
                self.tree.built_mode = self.tree.lst_inferred_mode
                self.tree.built_mode_string = serialise_mode(self.tree.built_mode)
                self.tree.lst_inferred_lowest = level
                # Warn when inference is not certain
                if confidence < 1:
                    logger.info(f"Assumed balanced at level {level} with confidence {confidence:.0%}.")
                self.tree.lst_inferred_warning = None
                return
            
        self.tree.lst_inferred_mode = None
        self.tree.lst_inferred_lowest = None
        self.tree.lst_inferred_warning = "Could not infer a balanced rung."
        self.tree.built_mode = None
        self.tree.built_mode_string = None
