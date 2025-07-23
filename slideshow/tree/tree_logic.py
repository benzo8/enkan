import slideshow.tree.Tree as Tree
from slideshow.tree.TreeNode import TreeNode
from slideshow.utils.Defaults import resolve_mode
from slideshow.constants import TOTAL_WEIGHT


def calculate_weights(tree: Tree) -> None:
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

    def _process_node(
        node: "TreeNode",
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
            tree.defaults.mode | (node.children[0].mode_modifier or {}), child_level
        )

        children = _fill_missing_proportions(
            node.children,
            child_mode,
            slope,
            count_fn=(
                (lambda n: tree.count_branches(n)[1]) if child_mode == "w" else None
            ),
        )

        for child in children:
            child_weight = node.weight * (child.proportion / 100)
            _process_node(child, child_weight, mode_modifier)

    def _fill_missing_proportions(
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

    lowest_rung = min(tree.defaults.mode.keys())
    starting_nodes = tree.get_nodes_at_level(lowest_rung) or [tree.root]

    mode, slope = resolve_mode(tree.defaults.mode, lowest_rung)

    starting_nodes = _fill_missing_proportions(
        starting_nodes,
        mode,
        slope,
        count_fn=(lambda n: tree.count_branches(n)[1]) if mode == "w" else None,
    )

    for node in starting_nodes:
        apportioned_weight = TOTAL_WEIGHT * (node.proportion / 100)
        _process_node(node, apportioned_weight)


def extract_image_paths_and_weights_from_tree(
    tree: Tree, test_iterations: int = None
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
    traverse_node(tree.root)

    return all_images, weights
