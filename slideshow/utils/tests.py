import os
import random
from collections import defaultdict
from tqdm import tqdm

from slideshow.constants import TOTAL_WEIGHT
from slideshow.utils.Defaults import resolve_mode

def print_tree(
    defaults,
    node,
    indent: str = "",
    current_depth: int = 0,
    max_depth: int = None,
):
    """
    Recursively prints the tree structure, displaying each node's name, mode, level,
    proportion, weight modifier, weight, and number of images (if any).
    """
    if node is None:
        return  # Or raise an error

    if max_depth is not None and current_depth > max_depth:
        return

    num_images = len(node.images) if node.images else 0
    mode, _ = resolve_mode(
        defaults.mode | (node.mode_modifier if node.mode_modifier else {}),
        node.level,
    )
    percent_sign = "%" if node.is_percentage else ""
    if num_images == 0:
        print(
            f"\033[90m{indent}{node.name} ({mode}{node.level}, P: {node.proportion}, M: {node.weight_modifier}{percent_sign}, W: {node.weight})\033[0m"
        )
    else:
        print(
            f"{indent}{node.name} ({mode}{node.level}, P: {node.proportion}, M: {node.weight_modifier}{percent_sign}, W: {node.weight}, Images: {num_images})"
        )

    for child in node.children:
        print_tree(defaults, child, indent + " + ", current_depth + 1, max_depth)

def test_distribution(image_nodes, weights, iterations, testdepth, defaults, quiet=False):    
    hit_counts = defaultdict(int)
    for _ in tqdm(range(iterations), desc="Iterating tests", disable=quiet):
        if defaults.is_random:
            image_path = random.choice(image_nodes)
        else:
            image_path = random.choices(image_nodes, weights=weights, k=1)[0]
        hit_counts["\\".join(image_path.split("\\")[:testdepth])] += 1

    directory_counts = defaultdict(int)
    for path, count in hit_counts.items():
        if os.path.isfile(path):
            directory = os.path.dirname(path)
        else:
            directory = path
        directory_counts[directory] += count

    total_images = len(image_nodes)
    for directory, count in sorted(directory_counts.items()):  # Alphabetical order
        print(
            f"Directory: {directory}, Hits: {count}, %age: {count / iterations * 100:.2f}%, Weight: {count / total_images * TOTAL_WEIGHT:.2f}"
        )
        
def test_node_lookup_consistency(tree) -> bool:
    """
    Test that every entry in tree.node_lookup has a key matching its node's name.
    Prints mismatches and returns True if all are consistent, False otherwise.

    Args:
        tree (Tree): The Tree instance to check.

    Returns:
        bool: True if all keys match node names, False otherwise.
    """
    all_good = True
    for key, node in tree.node_lookup.items():
        if key != node.name:
            print(f"Mismatch: key='{key}' != node.name='{node.name}'")
            all_good = False
    if all_good:
        print("node_lookup consistency check PASSED.")
    else:
        print("node_lookup consistency check FAILED.")
    return all_good