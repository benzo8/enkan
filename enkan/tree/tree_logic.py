from __future__ import annotations
import logging
from typing import Callable, Literal, Mapping, Optional, Sequence, Tuple, List

from .Tree import Tree
from .TreeBuilder import TreeBuilder
from .TreeNode import TreeNode
from enkan.utils.Defaults import Defaults, resolve_mode
from enkan.utils.tests import report_branch_weight_sums
from enkan.utils.Filters import Filters
from enkan.constants import TOTAL_WEIGHT

logger: logging.Logger = logging.getLogger("__name__")


def build_tree(
    defaults: Defaults,
    filters: Filters,
    image_dirs: Mapping[str, dict],
    specific_images: Optional[Mapping[str, dict]],
    quiet: bool = False,
) -> Tree:
    tree = Tree(defaults, filters)
    builder = TreeBuilder(tree)
    builder.build_tree(image_dirs, specific_images, quiet)
    tree.record_built_mode()
    _, num_images = tree.count_branches(tree.root)
    if num_images == 0:
        raise ValueError("No images found in the provided input files.")
    calculate_weights(tree)
    return tree


def calculate_weights(tree: Tree, ignore_user_proportion: bool = False) -> None:
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
        node: TreeNode,
        apportioned_weight: float,
        mode_modifier: Optional[dict] = None,
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

        children: List[TreeNode] = _fill_missing_proportions(
            node.children,
            child_mode,
            slope,
            count_fn=(
                (lambda n: tree.count_branches(n)[1]) if child_mode == "w" else None
            ),
        )

        for child in children:
            proportion = child.proportion if child.proportion is not None else 0
            child_weight = node.weight * (proportion / 100)
            _process_node(child, child_weight, mode_modifier)

    def _fill_missing_proportions(
        nodes: List[TreeNode],
        mode: str,
        slope: Tuple[int, int] | Sequence[int] = (0, 0),
        count_fn: Optional[Callable[[TreeNode], int]] = None,
    ) -> List[TreeNode]:
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
            per_node: float = remaining / len(unset_nodes)
            for n in unset_nodes:
                n.proportion = per_node
        elif mode == "w":
            # Weighted mode requires count_fn
            if not count_fn:
                # Fallback: treat like balanced if count function missing
                per_node = remaining / len(unset_nodes) if unset_nodes else 0
                for n in unset_nodes:
                    n.proportion = per_node
            else:
                slope_value: int | Sequence[int] = (
                    slope[0] if isinstance(slope, (list, tuple)) else slope
                )
                image_counts: List[int] = [
                    max(1, count_fn(n)) for n in unset_nodes
                ]  # avoid zero
                if slope_value >= 0:
                    exp = 1 - (slope_value / 100)
                    exp: float = max(0.01, exp)
                    powered: List[int] = [c**exp for c in image_counts]
                else:
                    exp = 1 + (slope_value / 100)
                    exp = max(0.01, exp)
                    powered = [(1 / c) ** exp for c in image_counts]
                total_powered: int = sum(powered) or 1
                for n, p in zip(unset_nodes, powered):
                    n.proportion = remaining * (p / total_powered)

        # Renormalize to exactly 100
        total: float | Literal[0] = sum(
            n.proportion for n in nodes if n.proportion is not None
        )
        if total:
            factor: float = 100 / total
            for n in nodes:
                if n.proportion is not None:
                    n.proportion *= factor
        return nodes

    def _reset_proportions(node: TreeNode) -> None:
        if not ignore_user_proportion and node.user_proportion is not None:
            node.proportion = float(node.user_proportion)
        else:
            node.proportion = None
        for child in node.children:
            _reset_proportions(child)

    _reset_proportions(tree.root)

    lowest_rung: int = min(tree.defaults.mode.keys())
    starting_nodes: List[TreeNode] = tree.get_nodes_at_level(lowest_rung) or [tree.root]

    mode, slope = resolve_mode(tree.defaults.mode, lowest_rung)

    starting_nodes = _fill_missing_proportions(
        starting_nodes,
        mode,
        slope,
        count_fn=(lambda n: tree.count_branches(n)[1]) if mode == "w" else None,
    )

    for node in starting_nodes:
        if node.proportion is None:
            # If still unset, give remaining equally (single node fallback)
            node.proportion = 100.0
        apportioned_weight: float = TOTAL_WEIGHT * (node.proportion / 100)
        _process_node(node, apportioned_weight)

    # DIAGNOSTIC REPORT (optional)
    if logger.isEnabledFor(logging.DEBUG):
        report_branch_weight_sums(starting_nodes)


def extract_image_paths_and_weights_from_tree(
    tree: Tree, start_node: TreeNode = None, test_iterations: int = None
) -> tuple[list[str], list[float]]:
    """
    Recursively extract all image file paths and their associated normalized weights from the tree.

    This function traverses the tree starting from the root node, collecting all image paths and
    calculating a normalized weight for each image based on the node's weight and the number of images
    in the node. If test_iterations is provided, the image name is used instead of the full path for testing.

    Args:
        tree (Tree): The tree from which to extract image paths and weights.
        start_node (TreeNode, optional): The node from which to start the traversal. If None, starts from the root.
        test_iterations (int, optional): If provided, use node names instead of image paths for output
            (useful for testing distributions). Defaults to None.

    Returns:
        tuple[list[str], list[float]]: A tuple containing:
            - all_images (list of str): List of image file paths (or node names if test_iterations is set).
            - weights (list of float): List of normalized weights corresponding to each image.
    """
    all_images: List[str] = []
    weights: List[float] = []

    # Helper function to recursively gather data
    def traverse_node(node: Optional[TreeNode]) -> None:
        if not node:
            return
        num_images = len(node.images)
        if num_images:
            normalised_weight = node.weight / (
                num_images if node.is_percentage else node.weight_modifier
            )
            target_value = node.name if test_iterations is not None else None
            for img in node.images:
                all_images.append(target_value or img)
                weights.append(normalised_weight)
        for child in node.children:
            traverse_node(child)

    if start_node is None:
        start_node = tree.root
    traverse_node(start_node)

    return all_images, weights
