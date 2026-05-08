from __future__ import annotations

import logging
import os

from typing import Iterable, List, Optional, Tuple
from enkan.tree.tree_io import load_tree_if_current
from enkan.tree.tree_logic import build_tree
from enkan.tree.tree_logic import apply_mode_and_recalculate
from enkan.utils.input.InputProcessor import InputProcessor
from enkan.utils.utils import find_input_file
from enkan.utils.BuildState import BuildState
from enkan.utils.Mode import Mode, copy_mode_map, serialise_mode
from enkan.utils.Filters import BuildFilters
from enkan.utils.input.SourceScope import SourceScope
from enkan.utils.input.input_models import LoadedSource, SourceKind, classify_input_path
from enkan.utils.input.TreeMerger import TreeMerger

logger = logging.getLogger(__name__)


class MultiSourceBuilder:
    """
    Build a single Tree from multiple heterogeneous inputs by normalising
    each to a Tree and merging left-to-right.
    """

    def __init__(self, build_state: BuildState, build_filters: BuildFilters) -> None:
        self.build_state = build_state
        self.build_filters = build_filters

    def build(self, input_files: Iterable[str], *, tk_root=None, tk_enabled: bool = True):
        sources: List[LoadedSource] = []
        builder_warnings: List[str] = []
        target_mode = self.build_state.cli_mode if self.build_state.cli_mode_pinned else None
        target_lowest_level = min(target_mode.keys()) if target_mode else None
        if target_mode:
            logger.info(
                "CLI mode detected; target mode set to %s (lowest rung %s).",
                target_mode,
                target_lowest_level,
            )
        else:
            logger.info(
                "No CLI mode; will derive target mode from the first source that declares one."
            )

        # Stage 1: Process each input file
        pending: List[str] = list(input_files)
        idx = 0
        while idx < len(pending):
            entry = pending[idx]
            additional_search_paths = [os.path.dirname(entry)]
            entry_path_full = find_input_file(entry, additional_search_paths)
            if not entry_path_full:
                entry_path_full = entry  # Probably a folder or invalid path
            kind = classify_input_path(entry_path_full)
            tree = None
            graft_offset = 0
            nested_entries: List[str] = []

            detected_mode = None

            match kind:
                case SourceKind.TREE:
                    tree = load_tree_if_current(entry_path_full)
                    if tree:
                        logger.info("Loaded tree source '%s'.", entry_path_full)
                    else:
                        # Try to fall back to txt if tree is stale/unreadable
                        msg = f"Skipping stale or unreadable tree '{entry_path_full}'."
                        logger.warning(msg)
                        builder_warnings.append(msg)
                        fallback_txt = os.path.splitext(entry_path_full)[0] + ".txt"
                        if os.path.isfile(fallback_txt):
                            pending.insert(idx + 1, fallback_txt)
                            logger.info(
                                "Queued txt fallback '%s' for outdated tree '%s'.",
                                fallback_txt,
                                entry_path_full,
                            )
                        else:
                            msg = f"No txt fallback found for '{entry_path_full}'."
                            logger.warning(msg)
                            builder_warnings.append(msg)                    

                case SourceKind.LST:
                    logger.info("Rebuilding tree from list '%s'.", entry_path_full)
                    tree = build_tree(
                        self.build_state,
                        self.build_filters,
                        kind="lst",
                        list_path=entry_path_full,
                        tk_root=tk_root,
                        tk_enabled=tk_enabled,
                    )
                case SourceKind.TXT | SourceKind.FOLDER:
                    logger.info(
                        "Processing txt/source '%s'.", entry_path_full)
                    tree, nested_entries, _, detected_mode = self._build_tree_from_entry(
                        entry_path_full,
                        graft_offset=graft_offset,
                        collector=builder_warnings,
                        tk_root=tk_root,
                        tk_enabled=tk_enabled,
                    )
                    if nested_entries:
                        for offset, nested_path in enumerate(nested_entries, start=1):
                            pending.insert(idx + offset, nested_path)

            # Try to infer mode from loaded tree if not from txt
            if tree:
                base_source, mode_info = self._build_loaded_source(
                    entry_path_full, kind, len(sources), tree, graft_offset
                )
                inferred_tree_mode, inferred_lowest = mode_info

                if inferred_tree_mode and not target_mode:
                    target_mode = inferred_tree_mode
                    target_lowest_level = inferred_lowest
                    logger.info(
                        "Adopted mode %s (lowest rung %s) from tree '%s'.",
                        target_mode,
                        target_lowest_level,
                        entry_path_full,
                    )

                sources.append(base_source)
                builder_warnings.extend(base_source.warnings)
            elif detected_mode and not target_mode:
                target_mode = detected_mode
                target_lowest_level = min(target_mode.keys())
                logger.info(
                    "Adopted mode %s (lowest rung %s) from txt '%s'.",
                    target_mode,
                    target_lowest_level,
                    entry_path_full,
                )

            idx += 1

        if not sources:
            return None, []
        if len(sources) == 1:
            # builder_warnings already includes per-source warnings
            single_warnings = list(dict.fromkeys(builder_warnings))
            self._finalize_tree(
                sources[0].tree,
                target_mode=target_mode,
                warnings=single_warnings,
            )
            return sources[0].tree, single_warnings

        # Stage 2: decide target mode and lowest rung
        if target_mode:
            self.build_state.set_mode(target_mode)
            target_lowest_level = min(target_mode.keys()) if target_mode else None
            logger.info(
                "Final target mode set to %s (lowest rung %s).",
                target_mode,
                target_lowest_level,
            )
            
        # Compute graft offsets for each source relative to target lowest rung
        if target_lowest_level is not None:
            for src in sources:
                if src.lowest_rung is not None:
                    src.graft_offset = target_lowest_level - src.lowest_rung
                else:
                    src.graft_offset = 0
        else:
            for src in sources:
                src.graft_offset = 0

        # Stage 3: Merge all sources
        merger = TreeMerger(target_lowest_level)
        result = merger.merge(sources)
        if result.added_nodes or result.updated_nodes:
            logger.info(
                "Merged inputs: %d node(s) added, %d node(s) updated.",
                result.added_nodes,
                result.updated_nodes,
            )
        result.warnings.extend(builder_warnings)

        self._finalize_tree(
            result.tree,
            target_mode=target_mode,
            warnings=result.warnings,
        )

        # Deduplicate warnings while preserving order
        deduped = list(dict.fromkeys(result.warnings))
        return result.tree, deduped

    def _build_tree_from_entry(
        self,
        entry: str,
        graft_offset: int = 0,
        collector: Optional[List[str]] = None,
        *,
        tk_root=None,
        tk_enabled: bool = True,
    ) -> Tuple[object | None, List[str], List[str], dict[int, object] | None]:
        """
        Use the existing InputProcessor to parse a single entry and
        materialise a Tree.
        """
        nested_paths: List[str] = []
        warnings_out: List[str] = collector if collector is not None else []
        source_scope = SourceScope.from_runtime(self.build_state, self.build_filters)
        processor = InputProcessor(source_scope.build_state, source_scope.build_filters)

        image_dirs, specific_images = (
            processor.process_input(
                entry,
                graft_offset=graft_offset,
                apply_global_mode=False,
                nested_paths=nested_paths,
            )
        )
        detected_mode = getattr(processor, "detected_mode", None)

        if image_dirs or specific_images:
            base_tree = build_tree(
                source_scope.build_state,
                source_scope.build_filters,
                image_dirs=image_dirs,
                specific_images=specific_images,
                mode=detected_mode,
                kind="txt",
                tk_root=tk_root,
                tk_enabled=tk_enabled,
            )
        else:
            base_tree = None
        if base_tree:
            return base_tree, nested_paths, warnings_out, detected_mode
        
        return None, nested_paths, warnings_out, detected_mode

    def _build_loaded_source(
        self,
        source_path: str,
        kind: SourceKind,
        order_index: int,
        tree,
        graft_offset: int = 0,
        provenance: Optional[str] = None,
    ) -> Tuple[LoadedSource, Tuple[dict[int, object] | None, int | None]]:
        mode_map = self._extract_tree_mode(tree)
        mode_string = getattr(tree, "built_mode_string", None)
        if not mode_string and hasattr(tree, "current_mode_string"):
            try:
                mode_string = tree.current_mode_string()
            except Exception:
                mode_string = None
        lowest_rung = min(mode_map.keys()) if mode_map else None
        warnings = self._collect_tree_warnings(tree)

        loaded = LoadedSource(
            source_path=source_path,
            kind=kind,
            order_index=order_index,
            tree=tree,
            mode=mode_map,
            mode_string=mode_string,
            lowest_rung=lowest_rung,
            graft_offset=graft_offset,
            provenance=provenance,
            warnings=warnings,
        )
        return loaded, (mode_map, lowest_rung)

    def _finalize_tree(
        self,
        tree,
        *,
        target_mode: dict[int, object] | None,
        warnings: List[str],
    ) -> None:
        if target_mode:
            self.build_state.set_mode(target_mode)
            try:
                apply_mode_and_recalculate(
                    tree,
                    self.build_state,
                    ignore_user_proportion=False,
                )
            except ValueError as exc:
                msg = str(exc)
                warnings.append(msg)
                logger.warning(msg)
                raise

        if self.build_state.cli_mode_pinned or getattr(tree, "built_mode", None) is not None:
            tree.built_mode = copy_mode_map(tree.build_state.mode)
            tree.built_mode_string = serialise_mode(tree.built_mode)
        tree.build_runtime_resolution_indexes()

    def _collect_tree_warnings(self, tree) -> List[str]:
        warnings: List[str] = []
        lst_warning = getattr(tree, "lst_inferred_warning", None)
        if lst_warning:
            warnings.append(lst_warning)
        build_warnings = getattr(tree, "build_warnings", None)
        if build_warnings:
            warnings.extend(build_warnings)
        return warnings

    def _extract_tree_mode(self, tree) -> dict[int, object] | None:
        if getattr(tree, "built_mode", None):
            return tree.built_mode
        mode_str = (
            tree.current_mode_string() if hasattr(tree, "current_mode_string") else None
        )
        if mode_str:
            return Mode.from_string(mode_str).map
        return None
