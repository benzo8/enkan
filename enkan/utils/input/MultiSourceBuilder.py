from __future__ import annotations

import logging
import os

from typing import Iterable, List, Optional
from enkan.tree.tree_io import load_tree_if_current
from enkan.tree.tree_logic import build_tree
from enkan.tree.tree_logic import calculate_weights, apply_mode_and_recalculate
from enkan.utils.input.InputProcessor import InputProcessor
from enkan.utils.utils import find_input_file
from enkan.utils.Defaults import Defaults, parse_mode_string
from enkan.utils.Filters import Filters
from enkan.utils.input.input_models import LoadedSource, SourceKind, classify_input_path
from enkan.utils.input.TreeMerger import TreeMerger
from enkan import constants

logger = logging.getLogger(__name__)


class MultiSourceBuilder:
    """
    Build a single Tree from multiple heterogeneous inputs by normalising
    each to a Tree and merging left-to-right.
    """

    def __init__(self, defaults: Defaults, filters: Filters) -> None:
        self.defaults = defaults
        self.filters = filters
        self.processor = InputProcessor(defaults, filters)

    def build(self, input_files: Iterable[str]):
        sources: List[LoadedSource] = []
        target_mode = self.defaults.args_mode
        target_lowest_level = min(target_mode.keys()) if target_mode else None
        if target_mode:
            self.defaults.set_global_defaults(mode=target_mode)
            logger.debug(
                "CLI mode detected; target mode set to %s (lowest rung %s).",
                target_mode,
                target_lowest_level,
            )
        else:
            logger.debug(
                "No CLI mode; will derive target mode from the first source that declares one."
            )

        for idx, entry in enumerate(input_files):
            additional_search_paths = [os.path.dirname(entry)]
            entry_path_full = find_input_file(entry, additional_search_paths)
            kind = classify_input_path(entry_path_full)
            tree = None
            graft_offset = 0

            if kind == SourceKind.TXT:
                detected_mode_dict, detected_lowest = self._detect_txt_global_mode(
                    entry_path_full
                )
                if target_mode is None and detected_mode_dict:
                    target_mode = detected_mode_dict
                    target_lowest_level = detected_lowest
                    self.defaults.set_global_defaults(mode=target_mode)
                    logger.debug(
                        "Derived target mode %s (lowest rung %s) from txt '%s'.",
                        target_mode,
                        target_lowest_level,
                        entry_path_full,
                    )
                if target_lowest_level is not None and detected_lowest is not None:
                    graft_offset = target_lowest_level - detected_lowest
                    logger.debug(
                        "Applying graft offset %s to '%s' (txt lowest %s -> target lowest %s).",
                        graft_offset,
                        entry_path_full,
                        detected_lowest,
                        target_lowest_level,
                    )
                else:
                    logger.debug(
                        "No global mode found in '%s'; using current defaults.",
                        entry_path_full,
                    )

            if target_mode:
                self.defaults.set_global_defaults(mode=target_mode)

            if kind == SourceKind.TREE:
                tree = load_tree_if_current(entry_path_full)
                if not tree:
                    logger.warning(
                        "Skipping stale or unreadable tree '%s'.", entry_path_full
                    )
                    continue
                logger.debug("Loaded tree source '%s'.", entry_path_full)
            elif kind == SourceKind.LST:
                logger.debug("Rebuilding tree from list '%s'.", entry_path_full)
                tree = build_tree(
                    self.defaults,
                    self.filters,
                    kind="lst",
                    list_path=entry_path_full,
                )
            else:
                logger.debug(
                    "Processing txt/source '%s' with graft offset %s.",
                    entry_path_full,
                    graft_offset,
                )
                tree = self._build_tree_from_entry(
                    entry_path_full, graft_offset=graft_offset
                )

            if tree:
                if kind != SourceKind.TXT and target_mode:
                    self._harmonise_tree_mode(
                        tree, target_mode, source_label=entry_path_full
                    )
                sources.append(
                    LoadedSource(
                        source_path=entry_path_full,
                        kind=kind,
                        order_index=idx,
                        tree=tree,
                        mode_string=getattr(tree, "built_mode_string", None),
                    )
                )

        if not sources:
            return None, []
        if len(sources) == 1:
            return sources[0].tree, sources[0].warnings

        self._apply_mode_precedence(sources)

        merger = TreeMerger()
        result = merger.merge(sources)
        if result.added_nodes or result.updated_nodes:
            logger.info(
                "Merged inputs: %d node(s) added, %d node(s) updated.",
                result.added_nodes,
                result.updated_nodes,
            )
        # Recalculate weights in case structure/content changed
        try:
            calculate_weights(result.tree)
        except ValueError as exc:
            msg = str(exc)
            result.warnings.append(msg)
            logger.warning(msg)
            raise
        return result.tree, result.warnings

    def _build_tree_from_entry(self, entry: str, graft_offset: int = 0):
        """
        Use the existing InputProcessor to parse a single entry and
        materialise a Tree.
        """
        nested_trees: List = []

        def _nested_handler(path: str, _graft_offset: int, _apply_global_mode: bool):
            ext = os.path.splitext(path)[1].lower()
            try:
                if ext == ".lst":
                    tree = build_tree(
                        self.defaults,
                        self.filters,
                        kind="lst",
                        list_path=path,
                    )
                    nested_trees.append(tree)
                    return {}, {}, [], []
                if ext == ".tree":
                    tree = load_tree_if_current(path)
                    if tree:
                        nested_trees.append(tree)
                    return {}, {}, [], []
            except Exception as exc:
                logger.warning("Failed to process nested input '%s': %s", path, exc)
            return {}, {}, [], []

        image_dirs, specific_images, all_images, _weights = (
            self.processor.process_input(
                entry,
                graft_offset=graft_offset,
                apply_global_mode=False,
                nested_file_handler=_nested_handler,
            )
        )

        if image_dirs or specific_images:
            base_tree = build_tree(
                self.defaults,
                self.filters,
                image_dirs=image_dirs,
                specific_images=specific_images,
                kind="txt",
            )
        else:
            base_tree = None

        if nested_trees:
            sources: List[LoadedSource] = []
            if base_tree:
                sources.append(
                    LoadedSource(
                        source_path=str(entry),
                        kind=SourceKind.TXT,
                        order_index=0,
                        tree=base_tree,
                    )
                )
            for idx, nested in enumerate(nested_trees, start=len(sources)):
                sources.append(
                    LoadedSource(
                        source_path="nested",
                        kind=SourceKind.OTHER,
                        order_index=idx,
                        tree=nested,
                    )
                )
            merger = TreeMerger()
            merged = merger.merge(sources)
            try:
                calculate_weights(merged.tree)
            except ValueError as exc:
                merged.warnings.append(str(exc))
                logger.warning(str(exc))
            return merged.tree

        if base_tree:
            return base_tree

        # If only a flat list of images/weights was provided, surface a warning and skip
        if all_images:
            logger.warning(
                "Entry '%s' produced a flat list; tree navigation not available.", entry
            )
        return None

    def _apply_mode_precedence(self, sources: List[LoadedSource]) -> None:
        """
        Apply mode precedence:
            CLI args (already in defaults) > first tree built_mode > existing defaults/global.
        """
        defaults = self.defaults
        if defaults.args_mode is not None:
            return

        # Prefer first source with a recorded built_mode
        for src in sources:
            tree = src.tree
            if tree and getattr(tree, "built_mode", None):
                defaults.set_global_defaults(mode=tree.built_mode)
                return
            if src.mode_string:
                # Fallback: parsed mode string on source (if ever set)
                from enkan.utils.Defaults import parse_mode_string

                defaults.set_global_defaults(mode=parse_mode_string(src.mode_string))
                return

    def _extract_tree_mode(self, tree) -> dict[int, object] | None:
        if getattr(tree, "built_mode", None):
            return tree.built_mode
        mode_str = (
            tree.current_mode_string() if hasattr(tree, "current_mode_string") else None
        )
        if mode_str:
            return parse_mode_string(mode_str)
        return None

    def _harmonise_tree_mode(
        self, tree, target_mode: dict[int, object], source_label: str | None = None
    ) -> None:
        current_mode = self._extract_tree_mode(tree)
        if current_mode == target_mode:
            return
        # Align tree defaults and recalc under the target mode
        self.defaults.set_global_defaults(mode=target_mode)
        try:
            apply_mode_and_recalculate(
                tree, self.defaults, ignore_user_proportion=False
            )
            if source_label:
                logger.info("Recalculated '%s' with harmonised mode.", source_label)
        except Exception as exc:
            logger.warning(
                "Failed to harmonise mode for '%s': %s",
                source_label or "source",
                exc,
            )

    def _detect_txt_global_mode(
        self, path: str
    ) -> tuple[Optional[dict[int, object]], Optional[int]]:
        """
        Lightweight scan of a txt file for a global mode modifier (e.g. [b6]).
        Returns the parsed mode dict and its lowest level, or (None, None) if absent/unreadable.
        """
        try:
            with open(path, "r", encoding="utf-8", buffering=65536) as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    mods = constants.MODIFIER_PATTERN.findall(line)
                    for mod in mods:
                        mod_content = mod.strip("[]").strip()
                        if constants.MODE_PATTERN.match(mod_content):
                            mode_dict = parse_mode_string(mod_content)
                            if mode_dict:
                                lowest = min(mode_dict.keys())
                                logger.debug(
                                    "Detected global mode %s (lowest rung %s) in txt '%s'.",
                                    mode_dict,
                                    lowest,
                                    path,
                                )
                                return mode_dict, lowest
                    # Stop once we hit a real path line; globals are expected up top
                    if mods:
                        continue
                    break
        except OSError as exc:
            logger.warning("Unable to read txt '%s' for mode detection: %s", path, exc)
        return None, None
