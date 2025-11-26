import tkinter as tk

from enkan.utils.Defaults import Defaults
from enkan.utils.Filters import Filters
from enkan.tree.Tree import Tree
from .mySlideshow import ImageSlideshow



def start_slideshow(
    tree: Tree, 
    all_image_paths: list,
    cum_weights: list,
    defaults: Defaults, 
    filters: Filters, 
    interval: int | float | None = None,
) -> None:
    """
    Start the slideshow using the given paths and weights.

    Args:
        all_image_paths (list): List of image paths.
        weights (list): List of weights corresponding to image paths.
        tree (Tree): Tree object containing the image hierarchy.
        defaults (object): Defaults object containing configuration.
    """

    root = tk.Tk()
    _ = ImageSlideshow(root, tree, all_image_paths, cum_weights, defaults, filters, interval)
    root.mainloop()