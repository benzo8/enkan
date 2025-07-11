# -----------------------------------------------------------------------------
# slideshow-new.py
#
# A Python script to create a slideshow from a list of files, with various
# modes and features including weighted, balanced, and random selection.
#
# Author:      John Sullivan
# Created:     2023-2025
# License:     MIT License
# Copyright:   (c) 2023-2025 John Sullivan
#
# Description:
#   This script builds a slideshow from directories or lists of images,
#   supporting advanced weighting, folder balancing, and navigation features.
#   It uses Tkinter for the GUI and Pillow for image handling.
#
# Usage:
#   python slideshow-new.py --input_file <file_or_folder> [options]
#
# Dependencies:
#   - Python 3.8+
#   - Pillow
#   - tqdm
#
# -----------------------------------------------------------------------------

# ——— Standard library ———
import argparse
import os
from datetime import datetime

# ——— Local ———
from slideshow import constants
from slideshow.utils.InputProcessor import InputProcessor
from slideshow.utils.Defaults import Defaults
from slideshow.utils.Filters import Filters
from slideshow.utils.tests import print_tree, test_distribution
from slideshow.tree.Tree import Tree
from slideshow.mySlideshow.mySlideshow import ImageSlideshow

# Argument parsing setup
def cx_type(s: str) -> str:
    """
    argparse “type” function: returns the string if it matches,
    otherwise raises ArgumentTypeError.
    """
    if not constants.CX_PATTERN.fullmatch(s):
        msg = (
            f"invalid Cx string {s!r}; "
            "must be one or more blocks of B or W followed by digits (case-insensitive), "
            "e.g. B1, W23, B1W2B300"
        )
        raise argparse.ArgumentTypeError(msg)
    return s.lower()

parser = argparse.ArgumentParser(description="Create a slideshow from a list of files.")
parser.add_argument(
    "--input_file",
    "-i",
    metavar="input_file",
    nargs="+",
    type=str,
    help="Input file(s) and/or folder(s) to build or .lst file to load",
)
parser.add_argument(
    "-o", "--output", action="store_true", help="Write output file and exit"
)
parser.add_argument("--run", dest="run", action="store_true", help="Run the slideshow")
parser.add_argument(
    "-m-",
    "--mode",
    type=cx_type,
    help="Mode string. One or more occurrences of B or W (case-insensitive) followed by digits, e.g. B12W3",
)
parser.add_argument(
    "--depth",
    type=int,
    help="Depth below which to combine all folders into one",
)
parser.add_argument(
    "--random", action="store_true", help="Start in Completely Random mode"
)
parser.add_argument(
    "--video", dest="video", action="store_true", help="Enable video playback"
)
parser.add_argument(
    "--no-video",
    "--nv",
    dest="video",
    action="store_false",
    help="Disable video playback",
)
parser.set_defaults(video=None)
parser.add_argument(
    "--no-mute", "--nm", dest="mute", action="store_false", help="Disable mute"
)
parser.set_defaults(mute=None)
parser.add_argument(
    "--quiet", "-q", action="store_true", help="Run in quiet mode (no output)"
)
parser.add_argument(
    "--test", metavar="N", type=int, help="Run the test with N iterations"
)
parser.add_argument(
    "--testdepth", type=int, default=None, help="Depth to display test results"
)
parser.add_argument("--printtree", action="store_true", help="Print the tree structure")
parser.add_argument("--version", action="version", version=f"%(prog)s {constants.VERSION}")
args = parser.parse_args()


def write_image_list(all_images, weights, input_files, mode_args, output_path):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = [
        f"# Written: {now}",
        f"# Input files: {', '.join(input_files)}",
        f"# Mode arguments: {mode_args}",
        "# Format: image_path,weight",
    ]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(header) + "\n")
        for img, w in zip(all_images, weights):
            f.write(f"{img},{w}\n")

def start_slideshow(all_image_paths, weights):
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
    slideshow = ImageSlideshow(root, all_image_paths, weights, defaults)  # noqa: F841
    root.mainloop()

def main(input_files, test_iterations=None, testdepth=None, printtree=None):
    # Parse input files and directories
    processor = InputProcessor(defaults, filters, quiet=False)
    image_dirs, specific_images, all_images, weights = processor.process_inputs(input_files)

    if not any([image_dirs, specific_images, all_images, weights]):
        raise ValueError("No images found in the provided input files.")

    if image_dirs or specific_images:
        # Instantiate and build the tree
        tree = Tree(defaults, filters)
        tree.build_tree(image_dirs, specific_images)
        tree.calculate_weights()

        # Print tree if requested
        if printtree:
            print_tree(defaults, tree.root, max_depth=testdepth)
            return

        # Extract paths and weights from the tree
        extracted_images, extracted_weights = (
            tree.extract_image_paths_and_weights_from_tree(test_iterations)
        )
        all_images.extend(extracted_images)
        weights.extend(extracted_weights)

    if args.output:
        # Build output filename
        base_names = [os.path.splitext(os.path.basename(f))[0] for f in args.input_file]
        output_name = "_".join(base_names) + ".lst"
        output_path = os.path.join(os.getcwd(), output_name)
        write_image_list(all_images, weights, args.input_file, args.mode, output_path)
        print(f"Output written to {output_path}")
        return

    # Test or start the slideshow
    if test_iterations:
        test_distribution(all_images, weights, test_iterations, testdepth, defaults, args.quiet)
    else:
        start_slideshow(all_images, weights)

if __name__ == "__main__":
    defaults = Defaults(args=args)
    filters = Filters()

    # Use args.input_file directly as a list
    input_files = args.input_file if args.input_file else []

    if args.run or args.output:
        main(input_files)
    elif args.printtree:
        main(input_files, testdepth=args.testdepth, printtree=True)
    elif args.test:
        main(
            input_files,
            test_iterations=args.test,
            testdepth=args.testdepth if args.testdepth else defaults.depth + 1,
        )
