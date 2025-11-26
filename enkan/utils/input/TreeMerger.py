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

    def __init__(self, target_lowest_rung: int | None = None) -> None:
        self.warnings: list[str] = []
        self.target_lowest_rung = target_lowest_rung

    def merge(self, sources: Iterable[LoadedSource]) -> MergeResult:
        iterator = iter(sources)
        try:
            first = next(iterator)
        except StopIteration:
            raise ValueError("No sources provided for merge")

        if not first.tree:
            raise ValueError("First source has no tree to merge")

        base = first.tree
        base_offset = getattr(first, "graft_offset", 0) or 0
        if base_offset != 0 and self.target_lowest_rung is not None:
            base = self._shift_tree(base, base_offset)
        added_total = 0
        updated_total = 0
        for src in iterator:
            if not src.tree:
                continue
            added, updated = self._merge_trees(
                base, src.tree, getattr(src, "graft_offset", 0) or 0
            )
            added_total += added
            updated_total += updated

        return MergeResult(tree=base, warnings=self.warnings, added_nodes=added_total, updated_nodes=updated_total)

    def _merge_trees(self, base: Tree, incoming: Tree, graft_offset: int) -> Tuple[int, int]:
        added = 0
        updated = 0
        for node in self._traverse(incoming.root):
            if node.path == ROOT_NODE_NAME:
                continue
            existing = self._find_matching_node(base, node)
            if existing:
                if self._merge_node(existing, node, base):
                    updated += 1
            else:
                self._add_node(base, node, graft_offset)
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

    def _merge_node(self, target: TreeNode, incoming: TreeNode, base: Tree) -> bool:
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
        if self._merge_virtual_images(target, incoming, base):
            changed = True
        return changed

    def _add_node(self, base: Tree, incoming: TreeNode, graft_offset: int) -> None:
        target_name, target_parent = self._resolve_target_names(base, incoming, graft_offset)
        base.ensure_parent_exists(target_parent)
        new_node = TreeNode(
            name=target_name,
            path=incoming.path,
            group = getattr(incoming, "group", None),
            weight_modifier=incoming.weight_modifier,
            is_percentage=incoming.is_percentage,
            proportion=incoming.proportion,
            user_proportion=getattr(incoming, "user_proportion", None),
            mode_modifier=incoming.mode_modifier,
            images=list(incoming.images),
        )
        if hasattr(incoming, "video"):
            setattr(new_node, "video", getattr(incoming, "video", None))
        base.add_node(new_node, target_parent)
        # carry over virtual_image_lookup mappings for new node
        if hasattr(base, "virtual_image_lookup") and hasattr(incoming, "images"):
            for img in incoming.images:
                base.virtual_image_lookup[img] = new_node
        # If grafting is needed, adjust leaf placement via Grafting
        if graft_offset and new_node.images:
            target_level = new_node.level + graft_offset
            if self.target_lowest_rung is not None and target_level < self.target_lowest_rung:
                msg = (
                    f"Grafting offset would place node '{incoming.path}' below lowest rung "
                    f"{self.target_lowest_rung}."
                )
                self.warnings.append(msg)
                raise ValueError(msg)
            from enkan.tree.Grafting import Grafting
            grafter = Grafting(base)
            grafter.handle_grafting(root=new_node.path, graft_level=target_level, group=new_node.group)

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

    def _merge_virtual_images(self, target: TreeNode, incoming: TreeNode, base: Tree) -> bool:
        """
        Ensure virtual_image_lookup entries from the incoming node exist on the base tree.
        """
        changed = False
        if hasattr(base, "virtual_image_lookup") and incoming.images:
            for img in incoming.images:
                if img not in base.virtual_image_lookup:
                    base.virtual_image_lookup[img] = target
                    changed = True
        return changed

    def _shift_tree(self, tree: Tree, offset: int) -> Tree:
        """
        Create a new tree with all nodes shifted up/down by offset levels.
        """
        shifted = Tree(tree.defaults, tree.filters)
        shifted.built_mode = getattr(tree, "built_mode", None)
        shifted.built_mode_string = getattr(tree, "built_mode_string", None)
        shifted.lst_inferred_mode = getattr(tree, "lst_inferred_mode", None)
        shifted.lst_inferred_lowest = getattr(tree, "lst_inferred_lowest", None)
        shifted.lst_inferred_warning = getattr(tree, "lst_inferred_warning", None)

        for node in self._traverse(tree.root):
            if node.path == ROOT_NODE_NAME:
                continue
            new_level = node.level + offset
            if self.target_lowest_rung is not None and new_level < self.target_lowest_rung:
                if node.images:
                    msg = (
                        f"Grafting offset would place images for node '{node.path}' below lowest rung "
                        f"{self.target_lowest_rung}."
                    )
                    self.warnings.append(msg)
                    raise ValueError(msg)
                # allow structural nodes below rung if they carry no images
            new_path = tree.set_path_to_level(node.path, new_level)
            new_name = shifted.convert_path_to_tree_format(new_path)
            parent_name = os.path.dirname(new_name)
            shifted.ensure_parent_exists(parent_name)
            cloned = TreeNode(
                name=new_name,
                path=node.path,
                weight_modifier=node.weight_modifier,
                is_percentage=node.is_percentage,
                proportion=node.proportion,
                user_proportion=getattr(node, "user_proportion", None),
                mode_modifier=node.mode_modifier,
                flat=getattr(node, "flat", False),
                images=list(node.images),
            )
            if hasattr(node, "video"):
                setattr(cloned, "video", getattr(node, "video", None))
            cloned.group = getattr(node, "group", None)
            shifted.add_node(cloned, parent_name)
            if hasattr(shifted, "virtual_image_lookup") and cloned.images:
                for img in cloned.images:
                    shifted.virtual_image_lookup[img] = cloned
        return shifted

    @staticmethod
    def _is_from_path(image_path: str, src_path: str) -> bool:
        """
        Determine if an image belongs to the given source path (directory or file), using dirname matching.
        """
        norm_src = os.path.normpath(src_path)
        img_dir = os.path.normpath(os.path.dirname(image_path))
        return img_dir == norm_src or img_dir.startswith(norm_src + os.path.sep)

    # ---------------------------- Graft alignment helpers ----------------------------

    def _resolve_target_names(
        self, base: Tree, incoming: TreeNode, graft_offset: int
    ) -> Tuple[str, str]:
        """
        Resolve target node name and parent; offset applied later via Grafting for leaves.
        """
        return incoming.name, os.path.dirname(incoming.name)
