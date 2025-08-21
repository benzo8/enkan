from __future__ import annotations

from typing import TYPE_CHECKING
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
        if group in t.defaults.groups:
            group_graft_level = t.defaults.groups[group].get("graft_level")
        else:
            group_graft_level = None
        graft_level = graft_level or group_graft_level
        if not graft_level:
            return

        current_node: TreeNode | None = t.find_node(root, lookup_dict=t.path_lookup)
        if not current_node:
            logger.debug(
                "Warning: Node '%s' not found for grafting. Skipping.", root
            )
            return
        current_node_parent: TreeNode | None = current_node.parent

        levelled_name: str = t.convert_path_to_tree_format(
            t.set_path_to_level(root, graft_level, group)
        )
        parent_path: str = os.path.dirname(levelled_name)
        parent_node: TreeNode = t.ensure_parent_exists(parent_path)

        # Detach from the old parent and graft to the new location
        t.detach_node(current_node)
        parent_node.add_child(current_node)
        t.rename_node_in_lookup(current_node.name, levelled_name)
        current_node.path = root

        # Rename and relevel child nodes
        t.rename_children(current_node, levelled_name)

        # Prune old parent node if empty
        node_to_check = current_node_parent
        while node_to_check and node_to_check != t.root:
            if not node_to_check.images and not node_to_check.children:
                parent = node_to_check.parent
                if parent:
                    parent.children = [
                        child for child in parent.children if child != node_to_check
                    ]
                # Remove from node_lookup if you want to keep it clean
                if node_to_check.name in t.node_lookup:
                    del t.node_lookup[node_to_check.name]
                node_to_check = parent
            else:
                break

        # Add mode_modifiers, if present
        group_config = t.defaults.groups.get(group)
        if group_config:
            mode_modifiers = group_config.get("mode_modifier")
            if mode_modifiers:
                for level, mode in mode_modifiers.items():
                    for child in current_node.get_nodes_at_level(level):
                        child.mode_modifier = {level: mode}
            t.set_proportion(group, current_node)
