# ——— Standard library ———
import os

# ——— Local ———
from slideshow.tree.TreeNode import TreeNode
from slideshow.utils import utils


class Tree:
    def __init__(self, defaults, filters):
        self.root = TreeNode("root", 0)
        self.node_lookup = {"root": self.root}
        self.path_lookup = {"root": self.root}
        self.virtual_image_lookup = {"root": self.root}
        self.defaults = defaults
        self.filters = filters

    def handle_grafting(self: "Tree", root: str, graft_level: int, group: str) -> None:
        """
        Graft a subtree to a new location in the tree at the specified level and apply group-specific configuration.

        This function moves (grafts) a node and its subtree from its current parent to a new parent node at the
        specified graft_level. It also applies any mode modifiers and proportions specified in the group configuration.
        If the old parent becomes empty after grafting, it is pruned from the tree.

        Args:
            root (str): The original root path of the node to be grafted.
            graft_level (int): The level in the tree to which the node should be grafted.
            group (str): The group name used to look up group-specific configuration.

        Returns:
            None. The tree structure is modified in-place.
        """
        # if not group:
        #     return
        # else:
        if group in self.defaults.groups:
            group_graft_level = self.defaults.groups[group].get("graft_level")
        else:
            group_graft_level = None
        graft_level = graft_level or group_graft_level
        if not graft_level:
            return

        current_node_name = self.convert_path_to_tree_format(root)
        current_node = self.find_node(current_node_name)
        if not current_node:
            print(
                f"Warning: Node '{current_node_name}' not found for grafting. Skipping."
            )
            return
        current_node_parent = current_node.parent

        levelled_name = self.convert_path_to_tree_format(
            self.set_path_to_level(root, graft_level, group)
        )
        parent_path = os.path.dirname(levelled_name)
        parent_node = self.ensure_parent_exists(parent_path)

        # Detach from the old parent and graft to the new location
        self.detach_node(current_node)
        parent_node.add_child(current_node)
        self.rename_node_in_lookup(current_node.name, levelled_name)
        current_node.name = levelled_name
        current_node.path = root

        # Rename and relevel child nodes
        self.rename_children(current_node, levelled_name)

        # Prune old parent node if empty
        node_to_check = current_node_parent
        while node_to_check and node_to_check != self.root:
            if not node_to_check.images and not node_to_check.children:
                parent = node_to_check.parent
                if parent:
                    parent.children = [
                        child for child in parent.children if child != node_to_check
                    ]
                # Remove from node_lookup if you want to keep it clean
                if node_to_check.name in self.node_lookup:
                    del self.node_lookup[node_to_check.name]
                node_to_check = parent
            else:
                break

        # Add mode_modifiers, if present
        group_config = self.defaults.groups.get(group)
        if group_config:
            mode_modifiers = group_config.get("mode_modifier")
            if mode_modifiers:
                for level, mode in mode_modifiers.items():
                    for child in current_node.get_nodes_at_level(level):
                        child.mode_modifier = {level: mode}
            self.set_proportion(group, current_node)

    def rename_children(self, parent_node, new_parent_name):
        """
        Traverse the subtree of the parent node and update the names
        of all child nodes to reflect the graft. Assumes levels are calculated dynamically.

        Args:
            parent_node (TreeNode): The grafted node whose children need updating.
            new_parent_name (str): The new name of the parent node after grafting.
        """
        for child in parent_node.children:
            # Calculate the new name for the child node
            child_basename = os.path.basename(child.name)
            new_name = os.path.join(new_parent_name, child_basename)
            child.name = new_name
            self.rename_node_in_lookup(child.name, new_name)
            # Recursively update the child's subtree
            self.rename_children(child, new_name)

    def rename_node_in_lookup(self: "Tree", old_name: str, new_name: str) -> None:
        """
        Rename a node in the tree and update node_lookup accordingly.

        Args:
            old_name (str): The current name (key) of the node in node_lookup.
            new_name (str): The new name to assign to the node and as the key in node_lookup.
        """
        node = self.node_lookup.pop(old_name, None)
        if node is not None:
            node.name = new_name
            self.node_lookup[new_name] = node

    def append_overwrite_or_update(self, path, level, node_data=None):
        """
        Add or update a node in the tree. If the node already exists, overwrite or update it.
        """
        # Convert path to match the format used in node_lookup
        # tree_path = self.convert_path_to_tree_format(path)

        # Ensure all parent nodes exist
        parent_path = self.find_parent_name(path)
        self.ensure_parent_exists(parent_path)

        node_name = self.convert_path_to_tree_format(path)
        parent_node_name = self.convert_path_to_tree_format(parent_path)
        node = self.find_node(node_name)
        if node:
            # Update node data if it exists
            node.weight_modifier = node_data["weight_modifier"]
            node.is_percentage = node_data["is_percentage"]
            node.proportion = node_data["proportion"]
            node.mode_modifier = node_data["mode_modifier"]
            """
            TODO: Fix adding images to existing virtual nodes without duplicating images in other node types
            """
            # node.images.extend(node_data["images"])
        else:
            # Create a new node and add it to the tree
            new_node = TreeNode(
                name=node_name,
                path=path,
                weight_modifier=node_data["weight_modifier"],
                is_percentage=node_data["is_percentage"],
                proportion=node_data["proportion"],
                mode_modifier=node_data["mode_modifier"],
                images=node_data["images"],
            )
            self.add_node(new_node, parent_node_name)

    def detach_node(self, node):
        """
        Detach a node from its parent and update parent/child relationships.

        Args:
            node (TreeNode): The node to be detached.
        """
        if node.parent:
            # Remove the node from its parent's children list
            node.parent.children = [
                child for child in node.parent.children if child != node
            ]
            # Clear the node's parent reference
            node.parent = None

    def add_node(self, new_node, parent_node_name):
        """
        Add a new node to the tree, ensuring the parent exists.

        Args:
            new_node (TreeNode): The node to be added.
            parent_name (str): The name of the parent node.

        Raises:
            ValueError: If the parent cannot be created or added for any reason.
        """
        # Find the parent node
        parent_node = self.find_node(parent_node_name)

        # Add the new node to the parent
        parent_node.add_child(new_node)
        self.node_lookup[new_node.name] = new_node
        self.path_lookup[new_node.path] = new_node

    def ensure_parent_exists(self, path):
        """
        Iteratively ensure all parent nodes exist from the root down to the specified parent_name.

        Args:
            path (str): The full path of the parent node to ensure exists.

        Returns:
            TreeNode: The parent node if `return_parent` is True, otherwise None.
        """
        path_components = path.split(os.path.sep)
        current_node_path = utils.get_drive_or_root(path_components[0])
        current_node = self.root

        for component in path_components[1:]:  # Skip the "root" component
            next_node_path = os.path.join(current_node_path, component)
            next_node_name = self.convert_path_to_tree_format(next_node_path)
            if next_node_name not in self.node_lookup:
                # Create the next node if it doesn't exist
                new_node = TreeNode(name=next_node_name, path=next_node_path)
                current_node.add_child(new_node)
                self.node_lookup[next_node_name] = new_node
                self.path_lookup[next_node_path] = new_node
                current_node = new_node
            else:
                # Move to the existing node
                current_node = self.node_lookup[next_node_name]

            current_node_path = next_node_path

        return current_node

    def convert_path_to_tree_format(self: "Tree", path: str) -> str:
        """
        Convert the path to match the format used in node_lookup (e.g., prefixed with 'root').
        Removes the drive letter and adds 'root' as the base.
        """
        # Remove the drive letter (e.g., "I:") from the path
        path_without_drive = os.path.splitdrive(path)[1]

        # Split the path into components and prepend "root"
        path_components = ["root"] + path_without_drive.strip(os.path.sep).split(
            os.path.sep
        )

        # Join the components back into a single path
        return os.path.join(*path_components).lower()

    def set_path_to_level(self, path, level, group=None):
        """
        Adjust the path to the specified level. If the level is less than the current level, truncate the path.
        If the level is greater than the current level, extend the path with placeholder folders.

        Args:
            path (str): The original path.
            level (int): The target level for the path.

        Returns:
            str: The adjusted path.
        """
        current_level = self.calculate_level(path)
        path_components = path.split(os.path.sep)

        # Normalize the drive component
        if len(path_components) > 0 and path_components[0].endswith(":"):
            path_components[0] += os.path.sep
        # Remove any empty components
        if group:
            extension_root = group
            for i in range(1, len(path_components) - 1):
                path_components[i] = f"{extension_root}_{i}"

        else:
            path_components = list(filter(lambda x: x != "", path_components))
            extension_root = "unamed"

        if level <= current_level:
            # Truncate the path
            truncated_components = (
                path_components[: level - 1]
                + path_components[len(path_components) - 1 :]
            )
            return os.path.join(*truncated_components)

        elif level > current_level:
            # Extend the path with placeholders
            extension = [
                f"{extension_root}_{i - 1}" for i in range(current_level, level)
            ]
            extended_components = (
                path_components[:-1] + extension + [path_components[-1]]
            )
            return os.path.join(*extended_components)

        # No adjustment needed
        return path

    def find_parent_name(self: "Tree", node_name: str) -> str:
        """
        Return the parent name (path) of a given node name.

        This function uses os.path.dirname to extract the parent path from the given node name.
        It is used to determine the parent node in the tree structure.

        Args:
            node_name (str): The name (path) of the node whose parent is to be found.

        Returns:
            str: The parent name (path) of the given node.
        """
        return os.path.dirname(node_name)

    def find_node(self: "Tree", name: str, lookup_dict: dict = None) -> "TreeNode":
        """
        Retrieve a node from the tree by its name using the specified lookup dictionary.

        Args:
            name (str): The name (or path) of the node to find.
            lookup_dict (dict): The dictionary to search (defaults to node_lookup).

        Returns:
            TreeNode: The node with the specified name, or None if not found.
        """
        if lookup_dict is None:
            lookup_dict = self.node_lookup
        return lookup_dict.get(name)

    def copy_subtree_as_tree(self, start_node):
        """
        Return a new Tree that is a deep copy of the subtree starting at the given node.
        The root of the new Tree will be a copy of the supplied node and its descendants.
        """
        # start_node = self.find_node(start_node_name)
        # if not start_node:
        #     raise ValueError(f"Node '{start_node_name}' not found in the tree.")

        # Recursive function to copy nodes
        def deep_copy_node(node):
            new_node = TreeNode(
                name=node.name,
                path=node.path,
                weight_modifier=getattr(node, 'weight_modifier', None),
                is_percentage=getattr(node, 'is_percentage', None),
                proportion=getattr(node, 'proportion', None),
                mode_modifier=getattr(node, 'mode_modifier', None),
                images=list(node.images) if hasattr(node, 'images') else [],
            )
            # Copy children recursively
            for child in node.children:
                child_copy = deep_copy_node(child)
                new_node.add_child(child_copy)
            return new_node

        # Create the new Tree
        new_tree = Tree(self.defaults, self.filters)
        new_tree.root = deep_copy_node(start_node)
        # Update node_lookup and path_lookup for the subtree
        def update_lookups(node):
            new_tree.node_lookup[node.name] = node
            new_tree.path_lookup[node.path] = node
            for child in node.children:
                update_lookups(child)
        update_lookups(new_tree.root)
        return new_tree

    def get_nodes_at_level(self: "Tree", target_level: int) -> list["TreeNode"]:
        """
        Retrieve all nodes in the tree at the specified level.

        This function traverses the tree starting from the root node and collects all nodes
        whose level matches the given target_level. Traversal stops at nodes that match the
        target level, so their children are not included.

        Args:
            target_level (int): The level (depth) in the tree to collect nodes from.
                The root node is typically level 1.

        Returns:
            list[TreeNode]: A list of TreeNode objects at the specified level.
        """
        nodes_at_level = []

        def traverse(node):
            if node.level == target_level:
                nodes_at_level.append(node)
                # Skip traversing children since this node is at the target level
                return
            for child in node.children:
                traverse(child)

        traverse(self.root)
        return nodes_at_level

    def calculate_level(self: "Tree", path: str) -> int:
        """
        Calculate the level (depth) of a given filesystem path.

        The level is determined by splitting the path using the OS-specific path separator
        and counting the number of non-empty components. This is used to determine the
        depth of a node in the tree structure.

        Args:
            path (str): The filesystem path to evaluate.

        Returns:
            int: The level (depth) of the path, where the root is level 1.
        """
        return len(
            list(filter(None, path.split(os.path.sep)))
        )  # Calculate level based on path depth

    def set_proportion(
        self: "Tree",
        group: str,
        current_node: "TreeNode",
    ) -> int | None:
        """
        Determine the effective graft level for a group and node, and set the group's proportion
        (if present) on the node at that level along the current_node's path.

        Returns group_graft_level if it exists, otherwise the lowest of:
        - the group's mode_modifier keys (if any)
        - the lowest graft_level among the node's children (if any child has it set)

        If group_config has a 'proportion', it is set on the node at the effective graft level.

        Args:
            group (str): The group name to look up in defaults.groups.
            current_node (TreeNode): The node whose children may have graft_level set.

        Returns:
            int or None: The effective graft level, or None if not found.
        """
        group_config = self.defaults.groups.get(group, {})
        if group_config is None:
            return None
        proportion = group_config.get("proportion", None)
        if proportion is not None:
            group_graft_level = group_config.get("graft_level")
            if group_graft_level is not None:
                effective_level = group_graft_level
            else:
                # Get lowest mode_modifier key if present
                mode_modifiers = group_config.get("mode_modifier")
                mode_modifier_level = None
                if mode_modifiers:
                    mode_modifier_level = min(mode_modifiers.keys())

                # Get lowest graft_level among children if present
                child_graft_levels = [
                    getattr(child, "graft_level", None)
                    for child in getattr(current_node, "children", [])
                    if getattr(child, "graft_level", None) is not None
                ]
                child_graft_level = (
                    min(child_graft_levels) if child_graft_levels else None
                )

                # Return the lowest of mode_modifier_level and child_graft_level (if either exists)
                candidates = [
                    lvl
                    for lvl in [mode_modifier_level, child_graft_level]
                    if lvl is not None
                ]
                effective_level = min(candidates) if candidates else None

            # Set the proportion if present

            if proportion is not None and effective_level is not None:
                # Traverse up from current_node to the node at effective_level
                node = current_node
                while node is not None and node.level > effective_level:
                    node = node.parent
                if node is not None and node.level == effective_level:
                    node.proportion = proportion

        return
    
    def count_branches(self, node: "TreeNode") -> tuple[int, int]:
        """
        Recursively count the number of branches and images in the tree starting from the given node.

        Args:
            node (TreeNode): The current node to start counting from.

        Returns:
            tuple[int, int]: A tuple (branch_count, image_count) where:
                - branch_count (int): The total number of branches (nodes with images) in the subtree.
                - image_count (int): The total number of images in the subtree.
        """
        if not node:
            return 0, 0

        branch_count = 0
        image_count = 0

        # Count current node as a branch if it has images
        if node.images:
            branch_count = 1
            image_count = len(node.images)

        # Recursively count branches and images in child nodes
        for child in node.children:
            child_branch_count, child_image_count = self.count_branches(child)
            branch_count += child_branch_count
            image_count += child_image_count

        return branch_count, image_count