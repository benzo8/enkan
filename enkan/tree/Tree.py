from __future__ import annotations

# --- Standard library ---
import os
from typing import Any, Optional, Literal

# --- Local ---
from .TreeNode import TreeNode
from enkan.constants import ROOT_NODE_NAME
from enkan.utils.Defaults import Defaults, serialise_mode, ModeMap
from enkan.utils.Filters import Filters


class Tree:
    PICKLE_VERSION = 3

    def __init__(self, defaults: Defaults, filters: Filters) -> None:
        # Use string path, not int
        self.root: TreeNode = TreeNode(name=ROOT_NODE_NAME, path=ROOT_NODE_NAME)
        self.node_lookup: dict[str, TreeNode] = {ROOT_NODE_NAME: self.root}
        self.path_lookup: dict[str, TreeNode] = {ROOT_NODE_NAME: self.root}
        self.virtual_image_lookup: dict[str, TreeNode] = {ROOT_NODE_NAME: self.root}
        self.defaults: Defaults = defaults
        self.filters: Filters = filters
        self.built_mode_string: Optional[str] = None
        self.built_mode: Optional[ModeMap] = None
        self._post_init_indexes()

    def _post_init_indexes(self) -> None:
        # Backward compatibility for older pickles
        if not hasattr(self, "virtual_image_lookup"):
            self.virtual_image_lookup = {}
        if not hasattr(self, "built_mode_string"):
            self.built_mode_string = None
        if not hasattr(self, "built_mode"):
            self.built_mode = None
        # Ensure newer TreeNode fields exist after unpickling older trees
        for node in getattr(self, "node_lookup", {}).values():
            if not hasattr(node, "user_proportion"):
                setattr(node, "user_proportion", None)
            if not hasattr(node, "group"):
                setattr(node, "group", None)
        if self.built_mode is not None and not self.built_mode_string:
            self.built_mode_string = serialise_mode(self.built_mode)
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
            group=node_data.get("group") if node_data else None,
            weight_modifier=node_data["weight_modifier"],
            is_percentage=node_data["is_percentage"],
            proportion=node_data["proportion"],
            user_proportion=node_data.get("user_proportion"),
            mode_modifier=node_data["mode_modifier"],
            images=node_data["images"],
        )
        self.add_node(new_node, self.convert_path_to_tree_format(parent_path))

    def update_node(self, node: TreeNode, node_data: dict | None = None) -> None:
        """
        Update only the attributes explicitly present as keys in node_data.

        node_data may contain any subset of:
            weight_modifier, is_percentage, proportion, user_proportion, mode_modifier, images

        Keys not present are left unchanged. (None values are applied-treat them as explicit.)
        """
        if node is None or not node_data:
            return

        if "weight_modifier" in node_data:
            node.weight_modifier = node_data["weight_modifier"]
        if "is_percentage" in node_data:
            node.is_percentage = node_data["is_percentage"]
        if "proportion" in node_data:
            node.proportion = node_data["proportion"]
        if "user_proportion" in node_data:
            node.user_proportion = node_data["user_proportion"]
        if "mode_modifier" in node_data:
            node.mode_modifier = node_data["mode_modifier"]
        if "images" in node_data:
            node.images = node_data["images"]
        if "group" in node_data:
            node.group = node_data["group"]

        """
        TODO: If later you want to merge images instead of replace, add a flag
              e.g. if node_data.get("append_images"): node.images.extend(...)
        """

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
        """
        Ensure that all intermediate nodes for the given path exist.

        Supports:
            - Tree-format names:     root\\foo\\bar\\baz
            - Windows drive paths:   C:\\foo\\bar\\baz
            - UNC paths:             \\\\server\\share\\dept\\set

        Not supported / rejected:
            - Relative paths (no drive, no UNC, not starting with 'root')
        """
        if not path:
            return self.root

        # Normalise separators
        norm: str = os.path.normpath(path)

        # Branch: tree-format (starts with 'root' component)
        if norm.lower() == ROOT_NODE_NAME:
            return self.root
        if norm.lower().startswith(ROOT_NODE_NAME + os.path.sep):
            parts = [p for p in norm.split(os.path.sep) if p]
            # parts[0] is 'root'; build from parts[1:]
            current_node: TreeNode = self.root
            built_path = ""  # store subtree path without 'root' prefix
            for segment in parts[1:]:
                built_path: str = segment if not built_path else os.path.join(built_path, segment)
                node_name: str = os.path.join(ROOT_NODE_NAME, *built_path.split(os.path.sep)).lower()
                node: TreeNode | None = self.node_lookup.get(node_name)
                if node is None:
                    node = TreeNode(name=node_name, path=built_path)
                    current_node.add_child(node)
                    self.node_lookup[node_name] = node
                    self.path_lookup[built_path] = node
                current_node = node
            return current_node

        # Windows UNC?
        is_unc: bool = norm.startswith("\\\\")
        drive, tail = os.path.splitdrive(norm)

        parts: list[str]
        start_index = 0
        built_path = ""

        if is_unc and not drive:
            parts = [p for p in norm.split(os.path.sep) if p]
            if len(parts) < 2:
                raise ValueError(f"Malformed UNC path: {path}")
            built_path = f"\\\\{parts[0]}\\{parts[1]}"
            start_index = 2
        else:
            if drive:
                parts = [p for p in tail.split(os.path.sep) if p]
                built_path = drive + os.path.sep  # e.g. 'C:\\'
            else:
                # Relative path => reject (we do not support)
                raise ValueError(f"Relative paths not supported: {path}")

        current_node = self.root

        for segment in parts[start_index:]:
            if built_path and not built_path.endswith(os.path.sep) and not built_path.startswith("\\\\"):
                next_path: str = os.path.join(built_path, segment)
            else:
                next_path = os.path.join(built_path, segment) if built_path else segment

            node_name = self.convert_path_to_tree_format(next_path)
            node = self.node_lookup.get(node_name)
            if node is None:
                node = TreeNode(name=node_name, path=next_path)
                current_node.add_child(node)
                self.node_lookup[node_name] = node
                self.path_lookup[next_path] = node

            current_node = node
            built_path = next_path

        return current_node

    def convert_path_to_tree_format(self, path: str) -> str:
        path_without_drive: str = os.path.splitdrive(path)[1]
        components: list[str] = [
            c for c in path_without_drive.strip(os.path.sep).split(os.path.sep) if c
        ]
        return os.path.join(ROOT_NODE_NAME, *components).lower()

    def current_mode_string(self) -> Optional[str]:
        return serialise_mode(self.defaults.mode or {})

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
