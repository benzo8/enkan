import os
import logging
from collections import defaultdict
from itertools import zip_longest

from enkan.constants import TOTAL_WEIGHT
from enkan.config import get_current_config
from enkan.plugables.FolderSelectionMemory import FolderSelectionMemory
from enkan.plugables.ImageProviders import ImageProviders
from enkan.utils.Mode import resolve_mode
from enkan.utils.progress import progress
from enkan.tree.TreeNode import TreeNode


logger: logging.Logger = logging.getLogger("enkan.tree.diagnostics")


def print_tree(
    build_state,
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
        return

    if max_depth is not None and current_depth > max_depth:
        return

    num_images = len(node.images) if node.images else 0
    mode, _ = resolve_mode(
        build_state.mode_with_modifiers(node.mode_modifier),
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
        print_tree(build_state, child, indent + " + ", current_depth + 1, max_depth)


def _normalise_test_models(test_models, build_state):
    if not test_models:
        return [get_current_config()("slideshow.provider")]
    if isinstance(test_models, str):
        items = [item.strip() for item in test_models.split(",")]
    else:
        items = [str(item).strip() for item in test_models]
    return [item for item in items if item]


def _resolve_test_provider(provider_registry, requested_name):
    if requested_name.startswith("image_provider_"):
        requested_name = requested_name.removeprefix("image_provider_")
    if requested_name in provider_registry:
        return requested_name
    prefixed = f"image_provider_{requested_name}"
    for name, func in provider_registry.items():
        if getattr(func, "__name__", None) == prefixed:
            return name
    raise ValueError(f"Unknown test model '{requested_name}'")


def _truncate_test_path(image_path, testdepth):
    if testdepth is None:
        return image_path
    return "\\".join(image_path.split("\\")[:testdepth])


def _directory_counts_for_model(
    provider_name,
    image_nodes,
    weights,
    cum_weights,
    iterations,
    testdepth,
):
    providers = ImageProviders()
    resolved_name = _resolve_test_provider(providers.providers, provider_name)
    folder_memory = FolderSelectionMemory()
    provider = providers.providers[resolved_name](
        image_nodes,
        weights=weights,
        cum_weights=cum_weights,
        folder_memory=folder_memory,
    )

    hit_counts = defaultdict(int)
    for _ in progress(range(iterations), desc=f"Testing {resolved_name}"):
        image_path = next(provider)
        if resolved_name == "controlled_random_weighted":
            folder_memory.record_folder(os.path.dirname(image_path))
        hit_counts[_truncate_test_path(image_path, testdepth)] += 1

    directory_counts = defaultdict(int)
    for path, count in hit_counts.items():
        directory = os.path.dirname(path) if os.path.isfile(path) else path
        directory_counts[directory] += count

    return resolved_name, dict(sorted(directory_counts.items()))


def _print_distribution_table(results_by_model, iterations, total_images):
    directories = sorted(
        {directory for counts in results_by_model.values() for directory in counts}
    )
    rows = []
    for directory in directories:
        row = [directory]
        for model_name, counts in results_by_model.items():
            count = counts.get(directory, 0)
            row.extend(
                [
                    str(count),
                    f"{count / iterations * 100:.2f}%",
                    f"{count / total_images * TOTAL_WEIGHT:.2f}",
                ]
            )
        rows.append(row)

    headers = ["Directory"]
    for model_name in results_by_model:
        headers.extend(
            [f"{model_name} hits", f"{model_name} %", f"{model_name} weight"]
        )

    widths = [
        max(len(str(cell)) for cell in column)
        for column in zip_longest(headers, *rows, fillvalue="")
    ]

    def _format_row(values):
        return " | ".join(
            f"{str(value):<{widths[idx]}}" for idx, value in enumerate(values)
        )

    print(_format_row(headers))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(_format_row(row))


def test_distribution(
    image_nodes,
    weights,
    cum_weights,
    iterations,
    testdepth,
    histo,
    build_state,
    test_models=None,
):
    models = _normalise_test_models(test_models, build_state)
    results_by_model = {}
    for model_name in models:
        resolved_name, counts = _directory_counts_for_model(
            model_name,
            image_nodes,
            weights,
            cum_weights,
            iterations,
            testdepth,
        )
        results_by_model[resolved_name] = counts

    _print_distribution_table(results_by_model, iterations, len(image_nodes))

    if histo:
        if len(results_by_model) != 1:
            logger.warning(
                "Histogram output only supports a single test model; skipping."
            )
        else:
            plot_distribution_histogram(
                next(iter(results_by_model.values())),
                iterations,
            )


def plot_distribution_histogram(directory_counts, iterations):
    import matplotlib.pyplot as plt

    """
    Plots a histogram of hit counts per directory, ordered from least to most.
    """

    sorted_items = sorted(directory_counts.items(), key=lambda x: x[1])

    labels = [f"{i}" for i, (_directory, _) in enumerate(sorted_items)]
    percentage = [count / iterations * 100 for _, count in sorted_items]

    plt.figure(figsize=(max(8, len(labels) // 2), 6))
    bars = plt.bar(labels, percentage)

    plt.xlabel("Directory (index)")
    plt.ylabel("Hits")
    plt.title("Distribution Histogram (Least to Most)")

    def on_move(event):
        for bar, (directory, percentage) in zip(bars, sorted_items):
            if bar.contains(event)[0]:
                plt.gca().set_title(f"{directory}\nHits: {percentage}")
                plt.draw()
                break
        else:
            plt.gca().set_title("Distribution Histogram (Least to Most)")
            plt.draw()

    plt.gcf().canvas.mpl_connect("motion_notify_event", on_move)

    plt.tight_layout()
    plt.show()


def test_node_lookup_consistency(tree) -> bool:
    """
    Test that every entry in tree.node_lookup has a key matching its node's name.
    Prints mismatches and returns True if all are consistent, False otherwise.
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


def _sum_leaf_image_weights(node: TreeNode) -> float:
    total = 0.0
    if node.images:
        if node.is_percentage:
            total += node.weight
        else:
            denom = node.weight_modifier if node.weight_modifier else 1
            total += (node.weight / denom) * len(node.images)
    for child in node.children:
        total += _sum_leaf_image_weights(child)
    return total


def _sum_node_weights(node: TreeNode) -> float:
    total = node.weight or 0.0
    for child in node.children:
        total += _sum_node_weights(child)
    return total


def report_branch_weight_sums(start_nodes: list[TreeNode]) -> None:
    lines: list[str] = []
    grand_leaf = 0.0
    grand_nodes = 0.0
    for start_node in start_nodes:
        leaf = _sum_leaf_image_weights(start_node)
        nodes_sum = _sum_node_weights(start_node)
        grand_leaf += leaf
        grand_nodes += nodes_sum
        lines.append(
            f"[weights] branch='{start_node.name}' "
            f"leaf_total={leaf:.4f} node_weight_sum={nodes_sum:.4f}"
        )
    lines.append(
        f"[weights] aggregate leaf_total={grand_leaf:.4f} "
        f"TOTAL_WEIGHT={TOTAL_WEIGHT:.4f} "
        f"(diff={grand_leaf - TOTAL_WEIGHT:.6f})"
    )
    for line in lines:
        logger.debug(line)
