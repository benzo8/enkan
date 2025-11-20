from __future__ import annotations

import os
import logging
from typing import Iterable, List, Tuple

from enkan.tree.tree_logic import build_tree
from enkan.tree.tree_logic import calculate_weights
from enkan.utils.InputProcessor import InputProcessor
from enkan.utils.Defaults import Defaults
from enkan.utils.Filters import Filters
from enkan.utils.input_models import LoadedSource, SourceKind, classify_input_path
from enkan.utils.list_tree_builder import build_tree_from_list
from enkan.utils.tree_merger import TreeMerger

logger = logging.getLogger(__name__)


class MultiSourceBuilder:
    """
    Build a single Tree from multiple heterogeneous inputs by normalising
    each to a Tree and merging left-to-right.
    """

    def __init__(self, defaults: Defaults, filters: Filters, quiet: bool = False) -> None:
        self.defaults = defaults
        self.filters = filters
        self.quiet = quiet
        self.processor = InputProcessor(defaults, filters, quiet)

    def build(self, input_files: Iterable[str]):
        sources: List[LoadedSource] = []
        for idx, entry in enumerate(input_files):
            kind = classify_input_path(entry)
            tree = None
            if kind == SourceKind.TREE:
                tree = self.processor._load_tree_if_current(entry)
                if not tree:
                    logger.warning("Skipping stale or unreadable tree '%s'.", entry)
                    continue
            elif kind == SourceKind.LST:
                tree = build_tree_from_list(entry, self.defaults, self.filters, self.quiet)
            else:
                tree = self._build_tree_from_entry(entry)

            if tree:
                sources.append(
                    LoadedSource(
                        source_path=entry,
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

    def _build_tree_from_entry(self, entry: str):
        """
        Use the existing InputProcessor to parse a single entry and
        materialise a Tree.
        """
        tree, image_dirs, specific_images, all_images, weights = self.processor.process_inputs([entry])
        if tree:
            return tree

        if image_dirs or specific_images:
            return build_tree(self.defaults, self.filters, image_dirs, specific_images, quiet=self.quiet)

        # If only a flat list of images/weights was provided, surface a warning and skip
        if all_images:
            logger.warning("Entry '%s' produced a flat list; tree navigation not available.", entry)
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
