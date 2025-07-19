from .mySlideshow import ImageSlideshow

def start_slideshow(all_image_paths, weights, defaults, filters, quiet):
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
    _ = ImageSlideshow(root, all_image_paths, weights, defaults, filters, quiet)
    root.mainloop()