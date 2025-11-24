from __future__ import annotations

import os

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

from enkan.constants import ROOT_NODE_NAME
from enkan.tree.Tree import Tree
from enkan.tree.TreeNode import TreeNode
from enkan.utils.input.input_models import LoadedSource


@dataclass
class MergeResult:
    tree: Tree
    warnings: list[str]
    added_nodes: int = 0
    updated_nodes: int = 0


class TreeMerger:
    """
    Merge trees left-to-right.
    Placement is owned by the earliest tree; later trees may append content and
    fill unset metadata but must not move nodes.
    """

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def merge(self, sources: Iterable[LoadedSource]) -> MergeResult:
        iterator = iter(sources)
        try:
            first = next(iterator)
        except StopIteration:
            raise ValueError("No sources provided for merge")

        if not first.tree:
            raise ValueError("First source has no tree to merge")

        base = first.tree
        added_total = 0
        updated_total = 0
        for src in iterator:
            if not src.tree:
                continue
            added, updated = self._merge_trees(base, src.tree)
            added_total += added
            updated_total += updated

        return MergeResult(tree=base, warnings=self.warnings, added_nodes=added_total, updated_nodes=updated_total)

    def _merge_trees(self, base: Tree, incoming: Tree) -> Tuple[int, int]:
        added = 0
        updated = 0
        for node in self._traverse(incoming.root):
            if node.path == ROOT_NODE_NAME:
                continue
            existing = self._find_matching_node(base, node)
            if existing:
                if self._merge_node(existing, node):
                    updated += 1
            else:
                self._add_node(base, node)
                added += 1
        return added, updated

    def _traverse(self, node: Optional[TreeNode]):
        if not node:
            return
        stack = [node]
        while stack:
            current = stack.pop()
            yield current
            stack.extend(current.children)

    def _merge_node(self, target: TreeNode, incoming: TreeNode) -> bool:
        """
        Apply merge semantics:
        - Preserve target placement/name.
        - Later input wins for user_proportion, weight_modifier, is_percentage, images, and graft/group metadata.
        - Replace images scoped to the incoming path only; leave other aliases intact (flatten/graft/group).
        """
        changed = False
        if self._replace_images_for_path(target, incoming):
            changed = True
        if self._merge_metadata(target, incoming):
            changed = True
        return changed

    def _add_node(self, base: Tree, incoming: TreeNode) -> None:
        parent_name = os.path.dirname(incoming.name)
        base.ensure_parent_exists(parent_name)
        new_node = TreeNode(
            name=incoming.name,
            path=incoming.path,
            weight_modifier=incoming.weight_modifier,
            is_percentage=incoming.is_percentage,
            proportion=incoming.proportion,
            user_proportion=getattr(incoming, "user_proportion", None),
            mode_modifier=incoming.mode_modifier,
            images=list(incoming.images),
        )
        if hasattr(incoming, "video"):
            setattr(new_node, "video", getattr(incoming, "video", None))
        base.add_node(new_node, parent_name)

    # ---------------------------- Helpers ----------------------------

    def _find_matching_node(self, base: Tree, incoming: TreeNode) -> Optional[TreeNode]:
        """
        Prefer matching on filesystem path first: if the path already exists in
        the base tree, reuse that node regardless of grafted parent in the
        incoming tree (placement in base wins). Only add a new node when the
        path is truly absent.
        """
        candidate = base.path_lookup.get(incoming.path) or base.path_lookup.get(os.path.normpath(incoming.path))
        if candidate:
            # If parents differ, keep base placement and just merge content.
            return candidate
        return None

    def _replace_images_for_path(self, target: TreeNode, incoming: TreeNode) -> bool:
        """
        Replace only the files belonging to the incoming path, leaving other aliases in shared nodes untouched.
        """
        if not incoming.images:
            return False

        incoming_path = os.path.normpath(incoming.path)
        kept = [img for img in target.images if not self._is_from_path(img, incoming_path)]
        new_images = kept + list(incoming.images)
        if new_images == target.images:
            return False
        target.images = new_images
        return True

    def _merge_metadata(self, target: TreeNode, incoming: TreeNode) -> bool:
        """
        Field precedence per architecture:
            - Left-most: name/location
            - Right-most: user_proportion, weight_modifier, is_percentage, images (handled separately), and graft/group metadata (if present externally)
            - Merge-when-empty: proportion, mode_modifier, video (as before)
        """
        changed = False

        # Right-most wins
        if getattr(incoming, "user_proportion", None) is not None and getattr(target, "user_proportion", None) != incoming.user_proportion:
            target.user_proportion = incoming.user_proportion
            changed = True
        if getattr(target, "weight_modifier", None) != getattr(incoming, "weight_modifier", None):
            target.weight_modifier = incoming.weight_modifier
            changed = True
        if getattr(target, "is_percentage", None) != getattr(incoming, "is_percentage", None):
            target.is_percentage = incoming.is_percentage
            changed = True

        # Merge-when-empty
        if target.proportion is None and incoming.proportion is not None:
            target.proportion = incoming.proportion
            changed = True
        if target.mode_modifier is None and incoming.mode_modifier is not None:
            target.mode_modifier = incoming.mode_modifier
            changed = True
        if hasattr(target, "video") and hasattr(incoming, "video"):
            if getattr(target, "video", None) is None and getattr(incoming, "video", None) is not None:
                target.video = incoming.video
                changed = True

        return changed

    @staticmethod
    def _is_from_path(image_path: str, src_path: str) -> bool:
        """
        Determine if an image belongs to the given source path (directory or file), using dirname matching.
        """
        norm_src = os.path.normpath(src_path)
        img_dir = os.path.normpath(os.path.dirname(image_path))
        return img_dir == norm_src or img_dir.startswith(norm_src + os.path.sep)
