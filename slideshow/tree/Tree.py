# ——— Standard library ———
import os

# ——— Third-party ———
from tqdm import tqdm

# ——— Local ———
from slideshow.constants import TOTAL_WEIGHT
from slideshow.tree.TreeNode import TreeNode
from slideshow.utils.Defaults import resolve_mode
from slideshow.utils import utils

class Tree:
    def __init__(self, defaults, filters):
        self.root = TreeNode("root", 0)
        self.node_lookup = {"root": self.root}
        self.defaults = defaults
        self.filters = filters
        
    def build_tree(self, image_dirs, specific_images, quiet=False):
        """
        Read image_dirs and specific_images and build a tree.
        """
        # Initialize tqdm progress bar
        with tqdm(
            total=0, desc="Building tree", unit="file", disable=quiet
        ) as pbar:
            for root, data in image_dirs.items():
                if data.get("flat", False):
                    self.add_flat_branch(root, data, pbar)
                else:
                    # Process each directory
                    self.process_directory(root, data, pbar)

                # Insert proportion & mode if specified
                if root in image_dirs:
                    if (
                        data.get("proportion") is not None
                        or data.get("mode_modifier") is not None
                    ):
                        # If a proportion is specified, use it
                        self.append_overwrite_or_update(
                            root,
                            data.get("level", self.calculate_level(root)),
                            data.get("depth", self.defaults.depth),
                            {
                                "weight_modifier": data.get("weight_modifier", 100),
                                "is_percentage": data.get("is_percentage", True),
                                "proportion": data.get("proportion"),
                                "mode_modifier": data.get("mode_modifier"),
                                "images": [],
                            },
                        )

                self.handle_grafting(root, data.get("graft_level"), data.get("group"))

        # Handle specific images if provided
        if specific_images:
            self.process_specific_images(specific_images)

    def process_directory(self, root, data, pbar):
        """
        Process a single root directory and add nodes to the tree.
        Handles image processing and grafting.
        """
        root_level = utils.level_of(root)
        depth = data.get("depth", self.defaults.depth)

        # Traverse the directory tree
        for path, dirs, files in os.walk(root):
            if self.filters.passes(path) == 0:
                # Update the total for new files discovered
                pbar.total += len(files)
                pbar.desc = f"Processing {path}"
                pbar.update(len(files))
                pbar.refresh()
                self.process_path(path, files, dirs, data, root_level, depth)
            elif self.filters.passes(path) == 1:
                del dirs[:]  # Prune directories

    def preprocess_ignored_files(self, ignored_files):
        """
        Preprocess ignored_dirs to extract directory paths.

        Args:
            ignored_dirs (list): List of ignored file paths.

        Returns:
            set: Set of directory paths containing ignored files.
        """
        ignored_files_dirs = set()
        for ignored in ignored_files:
            dir_path = os.path.dirname(ignored)  # Get the directory path
            ignored_files_dirs.add(dir_path)
        return ignored_files_dirs

    def process_files(self, path, files, filters, is_videoallowed=None):
        """
        Process files in the current directory, ignoring specified files.

        Args:
            path (str): Current directory path.
            files (list): List of files in the current directory.
            filters (object): Object containing ignored_dirs.

        Returns:
            list: List of valid image file paths.
        """
        # Preprocess ignored_dirs once (outside this function)
        if not hasattr(filters, "ignored_files_dirs"):
            filters.ignored_files_dirs = self.preprocess_ignored_files(
                filters.ignored_files
            )

        # Check if the current directory is in ignored_files_dirs
        if path in filters.ignored_files_dirs:
            # Filter out ignored files from the current directory
            valid_files = [
                f for f in files if os.path.join(path, f) not in filters.ignored_files
            ]
        else:
            # No ignored files in this directory
            valid_files = files

        # Filter for valid image files
        images = [
            os.path.join(path, f)
            for f in valid_files
            if utils.is_imagefile(f) or (utils.is_videofile(f) and is_videoallowed)
        ]

        return images

    def process_path(self, path, files, dirs, data, root_level, depth):
        """
        Process an individual path, adding images or virtual nodes as needed.
        """
        images = self.process_files(
            path, files, self.filters, utils.is_videoallowed(data.get("video"))
        )

        if not images:
            return

        path_level = self.calculate_level(path)
        path_depth = path_level - root_level

        if dirs:
            # Create a special "images" branch for directories with images
            self.add_images_branch(path, images, path_level + 1, depth, data)
        elif path_depth > depth:
            # Truncate to a virtual path
            self.add_virtual_branch(path, images, root_level, depth, data)
        else:
            # Add a regular branch
            self.add_regular_branch(path, images, path_level, depth, data)

    def add_flat_branch(self, path, data, pbar):
        """
        Add a special 'flat' branch for directories with images.
        """

        def flatten_branch(root):
            """
            Collect all images from the branch rooted at `root`, including subdirectories.

            Args:
                root (str): The root directory of the branch.

            Returns:
                list: A list of full paths to all images in the branch.
            """
            images = []
            for path, _, files in os.walk(root):
                images.extend(
                    os.path.join(path, f)
                    for f in files
                    if utils.is_imagefile(f)
                    or (utils.is_videofile(f) and utils.is_videoallowed(data.get("video")))
                )
            return images

        pbar.desc = f"Flattening {path}"
        pbar.refresh()

        images = flatten_branch(path)
        level = data.get("level", self.calculate_level(path))
        depth = data.get("depth", 9999)

        pbar.total += len(images)
        pbar.update(len(images))
        pbar.refresh()

        self.append_overwrite_or_update(
            path,
            level,
            depth,
            {
                "weight_modifier": data.get("weight_modifier", 100),
                "is_percentage": data.get("is_percentage", True),
                "proportion": None,
                "mode_modifier": data.get("mode_modifier"),
                "images": images,
            },
        )

    def add_images_branch(self, path, images, level, depth, data):
        """
        Add a special 'images' branch for directories with images.
        """
        images_path = os.path.join(path, "images")
        self.append_overwrite_or_update(
            images_path,
            level,
            depth,
            {
                "weight_modifier": 100,
                "is_percentage": True,
                "proportion": None,
                "mode_modifier": data.get("mode_modifier"),
                "images": images,
            },
        )

    def add_virtual_branch(self, path, images, root_level, depth, data):
        """
        Add a virtual branch when the path depth exceeds the allowed depth.

        TODO: Fix adding images to existing virtual branches.

        """
        virtual_path_level = root_level + depth
        virtual_path = os.path.join(
            *path.split(os.path.sep)[: virtual_path_level - 1], "Virtual"
        )
        self.append_overwrite_or_update(
            virtual_path,
            virtual_path_level,
            depth,
            {
                "weight_modifier": data.get("weight_modifier", 100),
                "is_percentage": data.get("is_percentage", True),
                "proportion": None,
                "mode_modifier": data.get("mode_modifier"),
                "images": images,
            },
        )

    def add_regular_branch(self, path, images, level, depth, data):
        """
        Add a regular branch for paths that don't need truncation.
        """
        self.append_overwrite_or_update(
            path,
            level,
            depth,
            {
                "weight_modifier": data.get("weight_modifier", 100),
                "is_percentage": data.get("is_percentage", True),
                "proportion": None,
                "mode_modifier": data.get("mode_modifier"),
                "images": images,
            },
        )

    def handle_grafting(
        self: "Tree", 
        root: str, 
        graft_level: int, 
        group: str
    ) -> None:
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
            self.rename_node_in_lookup(child.name, new_name)
            # Recursively update the child's subtree
            self.rename_children(child, new_name)

    def rename_node_in_lookup(
        self: "Tree",
        old_name: str,
        new_name: str
    ) -> None:
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

    def process_specific_images(self, specific_images):
        """
        Process specific images and add them to the tree.
        """
        num_average_images = int((lambda a, b: b / a)(*self.count_branches(self.root)))

        for path, data in specific_images.items():
            if self.filters.passes(path) == 0:
                node_name = path
                is_percentage = data.get("is_percentage", True)
                level = data.get("level", self.calculate_level(node_name))

                self.append_overwrite_or_update(
                    node_name,
                    level,
                    self.defaults.depth,
                    {
                        "weight_modifier": data.get("weight_modifier", 100),
                        "is_percentage": is_percentage,
                        "proportion": data.get("proportion", None),
                        "mode_modifier": data.get("mode_modifier", None),
                        "images": [path]
                        * (
                            num_average_images
                            if is_percentage
                            else data.get("weight_modifier", 100)
                        ),
                    },
                )

                # Handle grafting after processing the directory
                graft_level = data.get("graft_level") or level
                group = data.get("group")
                self.handle_grafting(node_name, graft_level, group)

    def append_overwrite_or_update(self, path, level, depth, node_data=None):
        """
        Add or update a node in the tree. If the node already exists, overwrite or update it.
        """
        # Convert path to match the format used in node_lookup
        tree_path = self.convert_path_to_tree_format(path)

        # Ensure all parent nodes exist
        tree_parent_name = self.find_parent_name(tree_path)
        self.ensure_parent_exists(tree_parent_name)

        node = self.find_node(tree_path)
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
                name=tree_path,
                path=path,
                weight_modifier=node_data["weight_modifier"],
                is_percentage=node_data["is_percentage"],
                proportion=node_data["proportion"],
                mode_modifier=node_data["mode_modifier"],
                images=node_data["images"],
            )
            self.add_node(new_node, tree_parent_name)

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

    def add_node(self, new_node, tree_parent_name):
        """
        Add a new node to the tree, ensuring the parent exists.

        Args:
            new_node (TreeNode): The node to be added.
            parent_name (str): The name of the parent node.

        Raises:
            ValueError: If the parent cannot be created or added for any reason.
        """
        # Find the parent node
        parent_node = self.find_node(tree_parent_name)

        # Add the new node to the parent
        parent_node.add_child(new_node)
        self.node_lookup[new_node.name] = new_node

    def ensure_parent_exists(self, parent_name):
        """
        Iteratively ensure all parent nodes exist from the root down to the specified parent_name.

        Args:
            parent_name (str): The full path of the parent node to ensure exists.

        Returns:
            TreeNode: The parent node if `return_parent` is True, otherwise None.
        """
        path_components = parent_name.split(os.path.sep)
        current_path = "root"
        current_node = self.root

        for component in path_components[1:]:  # Skip the "root" component
            next_path = os.path.join(current_path, component)

            if next_path not in self.node_lookup:
                # Create the next node if it doesn't exist
                new_node = TreeNode(name=next_path, path=None)
                current_node.add_child(new_node)
                self.node_lookup[next_path] = new_node
                current_node = new_node
            else:
                # Move to the existing node
                current_node = self.node_lookup[next_path]

            current_path = next_path

        return current_node

    def convert_path_to_tree_format(
        self: "Tree",
        path: str
    ) -> str:
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

    def find_parent_name(
        self: "Tree", 
        node_name: str
    ) -> str:
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

    def find_node(
        self: "Tree", 
        name: str
    ) -> "TreeNode":
        """
        Retrieve a node from the tree by its name using the node lookup dictionary.

        Args:
            name (str): The name (path) of the node to find.

        Returns:
            TreeNode: The node with the specified name, or None if not found.
        """
        return self.node_lookup.get(name)

    def get_nodes_at_level(
        self: "Tree", 
        target_level: int
    ) -> list["TreeNode"]:
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

    def calculate_level(
        self: "Tree", 
        path: str
    ) -> int:
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
                child_graft_level = min(child_graft_levels) if child_graft_levels else None

                # Return the lowest of mode_modifier_level and child_graft_level (if either exists)
                candidates = [lvl for lvl in [mode_modifier_level, child_graft_level] if lvl is not None]
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

    def extract_image_paths_and_weights_from_tree(
        self: "Tree", 
        test_iterations: int = None
    ) -> tuple[list[str], list[float]]:
        """
        Recursively extract all image file paths and their associated normalized weights from the tree.

        This function traverses the tree starting from the root node, collecting all image paths and
        calculating a normalized weight for each image based on the node's weight and the number of images
        in the node. If test_iterations is provided, the image name is used instead of the full path for testing.

        Args:
            test_iterations (int, optional): If provided, use node names instead of image paths for output
                (useful for testing distributions). Defaults to None.

        Returns:
            tuple[list[str], list[float]]: A tuple containing:
                - all_images (list of str): List of image file paths (or node names if test_iterations is set).
                - weights (list of float): List of normalized weights corresponding to each image.
        """
        all_images = []
        weights = []

        # Helper function to recursively gather data
        def traverse_node(node):
            if not node:
                return

            # Number of images in this node
            number_of_images = len(node.images)
            if number_of_images != 0:
                normalised_weight = node.weight / (
                    number_of_images if node.is_percentage else node.weight_modifier
                )

                # Add current node's images and normalized weights
                if test_iterations is None:
                    for img in node.images:
                        all_images.append(img)
                        weights.append(normalised_weight)
                else:
                    for img in node.images:
                        all_images.append(node.name)
                        weights.append(normalised_weight)

            # Recurse into children
            for child in node.children:
                traverse_node(child)

        # Start traversal from the root node
        traverse_node(self.root)

        return all_images, weights

    def count_branches(
        self, node: "TreeNode"
    ) -> tuple[int, int]:
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

    def calculate_weights(
        self: "Tree"
    ) -> None:
        """
        Calculates and assigns weights to all nodes in the tree based on the current mode and slope settings.

        This function determines the starting nodes at the lowest rung (level) of the tree, applies the appropriate
        mode and slope (as resolved from the defaults), fills in missing proportions for these nodes, and then
        recursively processes each node to assign weights throughout the tree.

        The weights are apportioned according to the calculated proportions and any weight modifiers present.
        This ensures that the final weights reflect the desired balancing or weighting strategy for the slideshow.

        Returns:
            None. The function updates the 'weight' attribute of each node in-place.
        """
        lowest_rung = min(self.defaults.mode.keys())
        starting_nodes = self.get_nodes_at_level(lowest_rung) or [self.root]

        mode, slope = resolve_mode(self.defaults.mode, lowest_rung)

        starting_nodes = self._fill_missing_proportions(
            starting_nodes,
            mode,
            slope,
            count_fn=(lambda n: self.count_branches(n)[1]) if mode == "w" else None,
        )

        for node in starting_nodes:
            apportioned_weight = TOTAL_WEIGHT * (node.proportion / 100)
            self._process_node(node, apportioned_weight)

    def _process_node(
        self, node: "TreeNode", 
        apportioned_weight: float,
        mode_modifier: dict = None,
    ) -> None:
        """
        Recursively assigns weights to a node and its children based on the apportioned weight and mode modifiers.

        This function applies the node's weight modifier, then, if the node has children, determines the mode and slope
        for the next level, fills missing proportions for the children, and recursively processes each child node.

        Args:
            node (TreeNode): The current node to process.
            apportioned_weight (float): The weight apportioned to this node from its parent.
            mode_modifier (dict, optional): Mode modifier dictionary to override or supplement the default mode.

        Returns:
            None. The function updates the 'weight' attribute of each node in-place and recurses through the tree.
        """
        # Apply node's weight_modifier
        node.weight = (
            apportioned_weight * (node.weight_modifier / 100)
            if node.is_percentage
            else apportioned_weight
        )

        if not node.children:
            return

        mode_modifier = node.mode_modifier or mode_modifier
        child_level = node.level + 1
        child_mode, slope = resolve_mode(
            self.defaults.mode | (node.children[0].mode_modifier or {}), child_level
        )

        children = self._fill_missing_proportions(
            node.children,
            child_mode,
            slope,
            count_fn=(
                (lambda n: self.count_branches(n)[1]) if child_mode == "w" else None
            ),
        )

        for child in children:
            child_weight = node.weight * (child.proportion / 100)
            self._process_node(child, child_weight, mode_modifier)

    def _fill_missing_proportions(
        self: "Tree",
        nodes: list[TreeNode],
        mode: str,
        slope: tuple[int, int] = (0, 0),
        count_fn: callable = None,
    ) -> list[TreeNode]:
        """
        Assigns proportions to nodes that do not have a set proportion, according to the specified mode.

        For 'balanced' mode ("b"), all unset nodes receive an equal share of the remaining proportion.
        For 'weighted' mode ("w"), proportions are assigned based on the number of images (or another count function)
        in each node, with an optional slope parameter to flatten, steepen, or invert the weighting.

        After assignment, all node proportions are normalized so their sum is 100.

        Args:
            nodes (list[TreeNode]): List of sibling nodes to assign proportions to.
            mode (str): Either "b" (balanced) or "w" (weighted).
            slope (tuple[int, int], optional): Slope parameter(s) for weighted mode, in the range -100 to 100.
                Only the first value is used. Positive values flatten toward balanced, negative values invert weighting.
            count_fn (callable, optional): Function to count items in a node (e.g., number of images).
                Required for weighted mode.

        Returns:
            list[TreeNode]: The list of nodes with updated 'proportion' attributes.
        """
        total_set = sum(n.proportion for n in nodes if n.proportion is not None)
        unset_nodes = [n for n in nodes if n.proportion is None]
        remaining = max(0, 100 - total_set)

        if not unset_nodes:
            return nodes

        if mode == "b":
            # Assign equal share of remaining proportion to each unset node
            per_node = remaining / len(unset_nodes)
            for n in unset_nodes:
                n.proportion = per_node
        elif mode == "w":
            # Assign proportion based on count_fn and slope
            slope_value = slope[0] if isinstance(slope, (list, tuple)) else slope
            image_counts = [count_fn(n) for n in unset_nodes]
            if slope_value >= 0:
                # Flatten toward balanced as slope increases
                exp = 1 - (slope_value / 100)
                exp = max(0.01, exp)
                powered = [count**exp for count in image_counts]
            else:
                # Inverse weighting for negative slopes
                exp = 1 + (slope_value / 100)  # slope -100 to 0 → exp 0 to 1
                exp = max(0.01, exp)
                powered = [(1 / count) ** exp for count in image_counts]
            total_powered = sum(powered) or 1
            for n, p in zip(unset_nodes, powered):
                n.proportion = remaining * (p / total_powered)

        # Renormalize so proportions sum to 100
        total = sum(n.proportion for n in nodes)
        for n in nodes:
            n.proportion = n.proportion * 100 / total if total else 0

        return nodes