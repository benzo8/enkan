from __future__ import annotations

# ——— Standard library ———
import os
from typing import Any, Optional, Literal

# ——— Local ———
from .TreeNode import TreeNode
from enkan.utils import utils
from enkan.utils.Defaults import Defaults
from enkan.utils.Filters import Filters


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
            child_basename: str = os.path.basename(child.name)
            new_name: str = os.path.join(new_parent_name, child_basename)
            old_name: str = child.name
            self.rename_node_in_lookup(old_name, new_name)
            self.rename_children(child, new_name)

    def rename_node_in_lookup(self, old_name: str, new_name: str) -> None:
        node: Optional[TreeNode] = self.node_lookup.pop(old_name, None)
        if node is not None:
            node.name = new_name
            self.node_lookup[new_name] = node

    def create_node(self, path: str, node_data: dict | None = None) -> None:
        parent_path: str = self.find_parent_name(path)
        self.ensure_parent_exists(parent_path)
        node_name: str = self.convert_path_to_tree_format(path)
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

    def update_node(self, node: TreeNode, node_data: dict | None = None) -> None:
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
        path_components: list[str] = path.split(os.path.sep)
        current_node_path: str = (
            utils.get_drive_or_root(path_components[0]) if path_components else ""
        )
        current_node: TreeNode = self.root

        for component in path_components[1:]:
            next_node_path: str = os.path.join(current_node_path, component)
            next_node_name: str = self.convert_path_to_tree_format(next_node_path)
            node: TreeNode | None = self.node_lookup.get(next_node_name)
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
        components: list[str] = [
            c for c in path_without_drive.strip(os.path.sep).split(os.path.sep) if c
        ]
        return os.path.join("root", *components).lower()

    def set_path_to_level(self, path: str, level: int, group: str | None = None) -> str:
        current_level: int = self.calculate_level(path)
        path_components: list[str] = path.split(os.path.sep)
        if path_components and path_components[0].endswith(":"):
            path_components[0] += os.path.sep

        if group:
            extension_root: str = group
            for i in range(1, len(path_components) - 1):
                path_components[i] = f"{extension_root}_{i}"
        else:
            path_components = [c for c in path_components if c]
            extension_root = "unamed"

        if level <= current_level:
            truncated: list[str] = path_components[: level - 1] + path_components[-1:]
            return os.path.join(*truncated)
        if level > current_level:
            extension: list[str] = [
                f"{extension_root}_{i - 1}" for i in range(current_level, level)
            ]
            extended: list[str] = (
                path_components[:-1] + extension + [path_components[-1]]
            )
            return os.path.join(*extended)
        return path

    def find_parent_name(self, node_name: str) -> str:
        return os.path.dirname(node_name)

    def find_node(
        self, name: str, lookup_dict: dict[str, TreeNode] | None = None
    ) -> TreeNode | None:
        if lookup_dict is None:
            lookup_dict = self.node_lookup
        return lookup_dict.get(name)

    def get_nodes_at_level(self, target_level: int) -> list[TreeNode]:
        result: list[TreeNode] = []

        def traverse(node: TreeNode) -> None:
            if node.level == target_level:
                result.append(node)
                return
            for c in node.children:
                traverse(c)

        traverse(self.root)
        return result

    def calculate_level(self, path: str) -> int:
        return len([c for c in path.split(os.path.sep) if c])

    def count_branches(self, node: TreeNode) -> tuple[int, int]:
        if not node:
            return 0, 0
        branches: Literal[1] | Literal[0] = 1 if node.images else 0
        images: int = len(node.images) if node.images else 0
        for child in node.children:
            b, i = self.count_branches(child)
            branches += b
            images += i
        return branches, images
