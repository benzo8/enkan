from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional
import os
import logging

from .Tree import Tree
from .TreeNode import TreeNode

if TYPE_CHECKING:  # pragma: no cover
    from .Tree import Tree

logger = logging.getLogger(__name__)


class Grafting:
    """Encapsulates subtree grafting logic for a Tree instance.

    A single instance of this class is attached to each Tree (see Tree.__init__).
    """

    def __init__(self, tree: "Tree") -> None:
        self.tree: Tree = tree

    def handle_grafting(
        self, root: str, graft_level: int | None, group: str | None
    ) -> None:
        """Graft a subtree to a new location in the tree.

        Args:
            root: The original root path of the node to be grafted.
            graft_level: The level in the tree to which the node should be grafted.
            group: The group name used to look up group-specific configuration.
        """
        t: Tree = self.tree

        # Resolve group graft level override
        group_config = t.defaults.groups.get(group) if group else None
        group_graft_level = group_config.get("graft_level") if group_config else None
        graft_level = graft_level or group_graft_level
        if not graft_level:
            return

        current_node: TreeNode | None = t.find_node(root, lookup_dict=t.path_lookup)
        if not current_node:
            logger.debug("Node '%s' not found for grafting. Skipping.", root)
            return
        current_node_parent: TreeNode | None = current_node.parent

        levelled_name: str = t.convert_path_to_tree_format(
            t.set_path_to_level(root, graft_level, group)
        )
        parent_path: str = os.path.dirname(levelled_name)
        parent_node: TreeNode = t.ensure_parent_exists(parent_path)

        # Detach and re-parent
        t.detach_node(current_node)
        parent_node.add_child(current_node)
        t.rename_node_in_lookup(current_node.name, levelled_name)
        current_node.path = root  # Preserve original filesystem path

        # Rename and re-index descendants
        t.rename_children(current_node, levelled_name)

        # Prune any now-empty ancestors from old location
        self._prune_empty_ancestors(current_node_parent)

        # Apply group-specific configuration (mode modifiers / proportions)
        if group_config:
            self._apply_group_config(current_node, group_config)

    # ---------------------------- Internal helpers ----------------------------

    def _prune_empty_ancestors(self, node: Optional[TreeNode]) -> None:
        """Remove now-empty ancestor chain (excluding root)."""
        t = self.tree
        while node and node != t.root:
            if not node.images and not node.children:
                parent = node.parent
                if parent:
                    parent.children = [c for c in parent.children if c is not node]
                t.node_lookup.pop(node.name, None)
                node = parent
            else:
                break

    def _apply_group_config(
        self, anchor: TreeNode, group_config: dict[str, Any]
    ) -> None:
        """
        Apply proportion (if any) and mode modifiers (if any) for a group to
        the subtree rooted at 'anchor'.

        precedence for proportion target level:
            1. explicit graft_level in group_config
            2. lowest mode_modifier level (if any)
            (else skip proportion)
        """
        proportion = group_config.get("proportion")
        mode_mods: dict[int, Any] | None = group_config.get("mode_modifier")

        # Proportion
        if proportion is not None:
            effective_level = group_config.get("graft_level") or (
                min(mode_mods.keys()) if mode_mods else None
            )
            if effective_level is not None:
                target_node = self._ascend_to_level(anchor, effective_level)
                if target_node and target_node.level == effective_level:
                    target_node.proportion = proportion

        # Mode modifiers
        if mode_mods:
            # Keys are absolute levels; assign only within this subtree.
            for lvl, mode in sorted(mode_mods.items()):
                for node in anchor.get_nodes_at_level(lvl):
                    # Merge or set mode modifier mapping
                    if isinstance(node.mode_modifier, dict):
                        node.mode_modifier[lvl] = mode
                    else:
                        node.mode_modifier = {lvl: mode}

    def _ascend_to_level(self, node: TreeNode, target_level: int) -> Optional[TreeNode]:
        """Ascend from node until level <= target_level; return that node (or None)."""
        cur = node
        while cur and cur.level > target_level:
            cur = cur.parent
        return cur
