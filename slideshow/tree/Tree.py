from __future__ import annotations

# ——— Standard library ———
import os
from typing import Any, Optional

# ——— Local ———
from .TreeNode import TreeNode
from slideshow.utils import utils
from slideshow.utils.Defaults import Defaults
from slideshow.utils.Filters import Filters


class Tree:
    PICKLE_VERSION = 2

    def __init__(self, defaults: Defaults, filters: Filters) -> None:
        # Use string path, not int
        self.root: TreeNode = TreeNode(name="root", path="root")
        self.node_lookup: dict[str, TreeNode] = {"root": self.root}
        self.path_lookup: dict[str, TreeNode] = {"root": self.root}
        self.virtual_image_lookup: dict[str, TreeNode] = {"root": self.root}
        self.defaults: Defaults = defaults
        self.filters: Filters = filters
        self._post_init_indexes()

    def _post_init_indexes(self) -> None:
        # Backward compatibility for older pickles
        if not hasattr(self, "virtual_image_lookup"):
            self.virtual_image_lookup = {}
        # (Add future index repairs here)

    def __getstate__(self) -> dict[str, Any]:
        state: dict[str, Any] = self.__dict__.copy()
        state["_pickle_version"] = self.PICKLE_VERSION
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)
        self._post_init_indexes()
        if "_pickle_version" not in self.__dict__:
            self._pickle_version = 0

    def rename_children(self, parent_node: TreeNode, new_parent_name: str) -> None:
        for child in parent_node.children:
            child_basename = os.path.basename(child.name)
            new_name = os.path.join(new_parent_name, child_basename)
            old_name = child.name
            self.rename_node_in_lookup(old_name, new_name)
            self.rename_children(child, new_name)

    def rename_node_in_lookup(self, old_name: str, new_name: str) -> None:
        node: Optional[TreeNode] = self.node_lookup.pop(old_name, None)
        if node is not None:
            node.name = new_name
            self.node_lookup[new_name] = node

    def append_overwrite_or_update(self, path: str, level: int, node_data: dict | None = None) -> None:
        parent_path: str = self.find_parent_name(path)
        self.ensure_parent_exists(parent_path)

        node_name: str = self.convert_path_to_tree_format(path)
        node: Optional[TreeNode] = self.find_node(node_name)
        if node:
            # Overwrite core attributes
            node.weight_modifier = node_data["weight_modifier"]
            node.is_percentage = node_data["is_percentage"]
            node.proportion = node_data["proportion"]
            node.mode_modifier = node_data["mode_modifier"]
            """
            TODO: Fix adding images to existing virtual nodes without duplicating images in other node types
            """
            # node.images.extend(node_data["images"])
        else:
            new_node: TreeNode = TreeNode(
                name=node_name,
                path=path,
                weight_modifier=node_data["weight_modifier"],
                is_percentage=node_data["is_percentage"],
                proportion=node_data["proportion"],
                mode_modifier=node_data["mode_modifier"],
                images=node_data["images"],
            )
            self.add_node(new_node, self.convert_path_to_tree_format(parent_path))

    def detach_node(self, node: TreeNode) -> None:
        if node.parent:
            node.parent.children = [c for c in node.parent.children if c is not node]
            node.parent = None

    def add_node(self, new_node: TreeNode, parent_node_name: str) -> None:
        parent_node: Optional[TreeNode] = self.find_node(parent_node_name)
        if parent_node is None:
            raise ValueError(f"Parent node '{parent_node_name}' not found.")
        parent_node.add_child(new_node)
        self.node_lookup[new_node.name] = new_node
        self.path_lookup[new_node.path] = new_node

    def ensure_parent_exists(self, path: str) -> TreeNode:
        path_components = path.split(os.path.sep)
        current_node_path = utils.get_drive_or_root(path_components[0]) if path_components else ""
        current_node: TreeNode = self.root

        for component in path_components[1:]:
            next_node_path = os.path.join(current_node_path, component)
            next_node_name = self.convert_path_to_tree_format(next_node_path)
            node = self.node_lookup.get(next_node_name)
            if node is None:
                node = TreeNode(name=next_node_name, path=next_node_path)
                current_node.add_child(node)
                self.node_lookup[next_node_name] = node
                self.path_lookup[next_node_path] = node
            current_node = node
            current_node_path = next_node_path
        return current_node

    def convert_path_to_tree_format(self, path: str) -> str:
        path_without_drive: str = os.path.splitdrive(path)[1]
        components = [c for c in path_without_drive.strip(os.path.sep).split(os.path.sep) if c]
        return os.path.join("root", *components).lower()

    def set_path_to_level(self, path: str, level: int, group: str | None = None) -> str:
        current_level = self.calculate_level(path)
        path_components = path.split(os.path.sep)
        if path_components and path_components[0].endswith(":"):
            path_components[0] += os.path.sep

        if group:
            extension_root = group
            for i in range(1, len(path_components) - 1):
                path_components[i] = f"{extension_root}_{i}"
        else:
            path_components = [c for c in path_components if c]
            extension_root = "unamed"

        if level <= current_level:
            truncated = path_components[: level - 1] + path_components[-1:]
            return os.path.join(*truncated)
        if level > current_level:
            extension = [f"{extension_root}_{i - 1}" for i in range(current_level, level)]
            extended = path_components[:-1] + extension + [path_components[-1]]
            return os.path.join(*extended)
        return path

    def find_parent_name(self, node_name: str) -> str:
        return os.path.dirname(node_name)

    def find_node(self, name: str, lookup_dict: dict[str, TreeNode] | None = None) -> TreeNode | None:
        if lookup_dict is None:
            lookup_dict = self.node_lookup
        return lookup_dict.get(name)

    def copy_subtree_as_tree(self, start_node: TreeNode) -> Tree:
        def deep_copy(node: TreeNode) -> TreeNode:
            new_node = TreeNode(
                name=node.name,
                path=node.path,
                weight_modifier=getattr(node, "weight_modifier", None),
                is_percentage=getattr(node, "is_percentage", None),
                proportion=getattr(node, "proportion", None),
                mode_modifier=getattr(node, "mode_modifier", None),
                images=list(getattr(node, "images", [])),
            )
            for child in node.children:
                new_node.add_child(deep_copy(child))
            return new_node

        new_tree = Tree(self.defaults, self.filters)
        new_tree.root = deep_copy(start_node)

        def index(node: TreeNode):
            new_tree.node_lookup[node.name] = node
            new_tree.path_lookup[node.path] = node
            for c in node.children:
                index(c)

        index(new_tree.root)
        return new_tree

    def get_nodes_at_level(self, target_level: int) -> list[TreeNode]:
        result: list[TreeNode] = []

        def traverse(node: TreeNode):
            if node.level == target_level:
                result.append(node)
                return
            for c in node.children:
                traverse(c)

        traverse(self.root)
        return result

    def calculate_level(self, path: str) -> int:
        return len([c for c in path.split(os.path.sep) if c])

    def set_proportion(self, group: str, current_node: TreeNode) -> int | None:
        group_config: dict[str, Any] | None = self.defaults.groups.get(group)
        if not group_config:
            return None
        proportion = group_config.get("proportion")
        if proportion is None:
            return None

        group_graft_level = group_config.get("graft_level")
        if group_graft_level is not None:
            effective_level = group_graft_level
        else:
            mode_modifiers = group_config.get("mode_modifier")
            mode_modifier_level = min(mode_modifiers.keys()) if mode_modifiers else None
            child_levels = [
                getattr(child, "graft_level", None)
                for child in current_node.children
                if getattr(child, "graft_level", None) is not None
            ]
            child_level = min(child_levels) if child_levels else None
            candidates = [lvl for lvl in (mode_modifier_level, child_level) if lvl is not None]
            effective_level = min(candidates) if candidates else None

        if effective_level is None:
            return None

        node = current_node
        while node and node.level > effective_level:
            node = node.parent
        if node and node.level == effective_level:
            node.proportion = proportion
        return effective_level

    def count_branches(self, node: TreeNode) -> tuple[int, int]:
        if not node:
            return 0, 0
        branches = 1 if node.images else 0
        images = len(node.images) if node.images else 0
        for child in node.children:
            b, i = self.count_branches(child)
            branches += b
            images += i
        return branches, images
