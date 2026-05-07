import tkinter as tk

from enkan.config import Config
from enkan.utils.BuildState import BuildState
from enkan.utils.Filters import RuntimeFilters
from enkan.utils.SelectionWeights import SelectionWeights
from enkan.tree.Tree import Tree
from enkan.tree.tree_logic import SelectionScope
from .mySlideshow import ImageSlideshow



def start_slideshow(
    tree: Tree, 
    all_image_paths: list,
    selection_weights: SelectionWeights,
    selection_scope: SelectionScope | None,
    build_state: BuildState,
    runtime_filters: RuntimeFilters,
    config: Config | None = None,
) -> None:
    """
    Start the slideshow using the given paths and weights.

    Args:
        all_image_paths (list): List of image paths.
        selection_weights (SelectionWeights): Weight data corresponding to image paths.
        tree (Tree): Tree object containing the image hierarchy.
        build_state: state used for runtime mode recalculation.
    """

    root = tk.Tk()
    _ = ImageSlideshow(
        root,
        tree,
        all_image_paths,
        selection_weights,
        selection_scope,
        build_state,
        runtime_filters,
        config,
    )
    root.mainloop()
