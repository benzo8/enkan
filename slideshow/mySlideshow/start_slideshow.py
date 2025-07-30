from .mySlideshow import ImageSlideshow

def start_slideshow(tree, all_image_paths, weights, defaults, filters, quiet, interval):
    """
    Start the slideshow using the given paths and weights.

    Args:
        all_image_paths (list): List of image paths.
        weights (list): List of weights corresponding to image paths.
        tree (Tree): Tree object containing the image hierarchy.
        defaults (object): Defaults object containing configuration.
    """
    import tkinter as tk

    root = tk.Tk()
    _ = ImageSlideshow(root, tree, all_image_paths, weights, defaults, filters, quiet, interval)
    root.mainloop()