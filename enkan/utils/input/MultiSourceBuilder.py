from __future__ import annotations

import logging
import os

from typing import Iterable, List
from enkan.tree.tree_io import load_tree_if_current
from enkan.tree.tree_logic import build_tree
from enkan.tree.tree_logic import calculate_weights, apply_mode_and_recalculate
from enkan.utils.input.InputProcessor import InputProcessor
from enkan.utils.utils import find_input_file
from enkan.utils.Defaults import Defaults, Mode
from enkan.utils.Filters import Filters
from enkan.utils.input.input_models import LoadedSource, SourceKind, classify_input_path
from enkan.utils.input.TreeMerger import TreeMerger

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
        builder_warnings: List[str] = []
        target_mode = self.defaults.args_mode
        target_lowest_level = min(target_mode.keys()) if target_mode else None
        if target_mode:
            logger.debug(
                "CLI mode detected; target mode set to %s (lowest rung %s).",
                target_mode,
                target_lowest_level,
            )
        else:
            logger.debug(
                "No CLI mode; will derive target mode from the first source that declares one."
            )

        # Process each input file
        for idx, entry in enumerate(input_files):
            additional_search_paths = [os.path.dirname(entry)]
            entry_path_full = find_input_file(entry, additional_search_paths)
            kind = classify_input_path(entry_path_full)
            tree = None
            graft_offset = 0
                    
            match kind:
                case SourceKind.TREE:
                    tree = load_tree_if_current(entry_path_full)
                    if not tree:
                        logger.warning(
                            "Skipping stale or unreadable tree '%s'.", entry_path_full
                        )
                        continue
                    logger.debug("Loaded tree source '%s'.", entry_path_full)
                        
                case SourceKind.LST:
                    logger.debug("Rebuilding tree from list '%s'.", entry_path_full)
                    tree = build_tree(
                        self.defaults,
                        self.filters,
                        kind="lst",
                        list_path=entry_path_full,
                    )
                case SourceKind.TXT:
                    logger.debug(
                        "Processing txt/source '%s' with graft offset %s.",
                        entry_path_full,
                        graft_offset,
                    )
                    tree = self._build_tree_from_entry(
                        entry_path_full, graft_offset=graft_offset
                    )

            if tree:
                inferred_tree_mode = self._extract_tree_mode(tree)
                if inferred_tree_mode and not target_mode:
                    target_mode = inferred_tree_mode
                    target_lowest_level = min(target_mode.keys())
                    self.defaults.set_global_defaults(mode=target_mode)
                    logger.debug(
                        "Adopted mode %s (lowest rung %s) from tree '%s'.",
                        target_mode,
                        target_lowest_level,
                        entry_path_full,
                    )

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
                        mode=getattr(tree, "built_mode", None)
                    )
                )

        if not sources:
            return None, []
        if len(sources) == 1:
            single_warnings = list(builder_warnings) + list(sources[0].warnings)
            return sources[0].tree, single_warnings

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
        result.warnings.extend(builder_warnings)
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
        detected_mode = getattr(self.processor, "detected_mode", None)
        # detected_lowest = getattr(self.processor, "detected_lowest", None)

        if image_dirs or specific_images:
            if detected_mode:
                self.defaults.set_global_defaults(mode=detected_mode)
            base_tree = build_tree(
                self.defaults,
                self.filters,
                image_dirs=image_dirs,
                specific_images=specific_images,
                mode=detected_mode,
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
                        mode=getattr(base_tree, "built_mode", None)
                    )
                )
            for idx, nested in enumerate(nested_trees, start=len(sources)):
                sources.append(
                    LoadedSource(
                        source_path="nested",
                        kind=SourceKind.OTHER,
                        order_index=idx,
                        tree=nested,
                        mode=getattr(nested, "built_mode", None)
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
            if tree and src.mode:
                defaults.set_global_defaults(mode=src.mode)
                return

    def _extract_tree_mode(self, tree) -> dict[int, object] | None:
        if getattr(tree, "built_mode", None):
            return tree.built_mode
        mode_str = (
            tree.current_mode_string() if hasattr(tree, "current_mode_string") else None
        )
        if mode_str:
            return Mode.from_string(mode_str).map
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
