import tkinter as tk

from enkan.config import Config
from enkan.utils.Defaults import Defaults
from enkan.utils.Filters import Filters
from enkan.utils.SelectionWeights import SelectionWeights
from enkan.tree.Tree import Tree
from enkan.tree.tree_logic import SelectionScope
from .mySlideshow import ImageSlideshow



def start_slideshow(
    tree: Tree, 
    all_image_paths: list,
    selection_weights: SelectionWeights,
    selection_scope: SelectionScope | None,
    defaults: Defaults, 
    filters: Filters, 
    config: Config | None = None,
) -> None:
    """
    Start the slideshow using the given paths and weights.

    Args:
        all_image_paths (list): List of image paths.
        selection_weights (SelectionWeights): Weight data corresponding to image paths.
        tree (Tree): Tree object containing the image hierarchy.
        defaults (object): Defaults object containing configuration.
    """

    root = tk.Tk()
    _ = ImageSlideshow(
        root,
        tree,
        all_image_paths,
        selection_weights,
        selection_scope,
        defaults,
        filters,
        config,
    )
    root.mainloop()
