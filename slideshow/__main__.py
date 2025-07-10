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
import re
from datetime import datetime

# ——— Third-party ———
from tqdm import tqdm

# ——— Local ———
from slideshow import constants

from slideshow.utils import utils
from slideshow.utils.Defaults import Defaults, parse_mode_string
from slideshow.utils.Filters import Filters
from slideshow.utils.tests import test_distribution
from slideshow.tree.Tree import Tree
from slideshow.slideshow.mySlideshow import ImageSlideshow

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

def process_inputs(input_files, defaults, recdepth=1):
    """
    Parse input files and directories to create image_dirs and specific_images dictionaries.

    Args:
        input_files (list): List of input files or directories.
        defaults (object): Defaults object containing configuration.

    Returns:
        tuple: (image_dirs, specific_images)
    """
    image_dirs = {}
    specific_images = {}
    all_images = []
    weights = []

    def find_input_file(input_filename, additional_search_paths=[]):
        # List of potential directories to search
        possible_locations = [
            os.path.dirname(os.path.abspath(__file__)),  # Script's directory
            os.getcwd(),  # Current working directory
            *additional_search_paths,  # Additional paths (e.g., main input file's directory)
            os.path.join(
                os.getcwd(), "lists"
            ),  # Fixed "lists" folder in the current working directory
        ]

        # If input_filename has no extension, try .lst then .txt
        base, ext = os.path.splitext(input_filename)
        candidates = [input_filename]
        if not ext:
            candidates = [input_filename + ".lst", input_filename + ".txt"]

        for location in possible_locations:
            for candidate in candidates:
                potential_path = os.path.join(location, candidate)
                if os.path.isfile(potential_path):
                    return potential_path

        return None

    def parse_input_line(line, defaults, recdepth):
        modifier_pattern = re.compile(r"(\[.*?\])")
        weight_modifier_pattern = re.compile(r"^\d+%?$")
        proportion_pattern = re.compile(r"^%\d+%?$")
        mode_pattern = constants.CX_PATTERN
        graft_pattern = re.compile(r"^g\d+$", re.IGNORECASE)
        group_pattern = re.compile(r"^>.*", re.IGNORECASE)
        depth_pattern = re.compile(r"^d\d+$", re.IGNORECASE)
        flat_pattern = re.compile(r"^f$", re.IGNORECASE)
        video_pattern = re.compile(r"^v$", re.IGNORECASE)
        no_video_pattern = re.compile(r"^nv$", re.IGNORECASE)
        mute_pattern = re.compile(r"^m$", re.IGNORECASE)
        no_mute_pattern = re.compile(r"^nm$", re.IGNORECASE)

        if line.startswith("[r]"):
            defaults.set_global_defaults(is_random=True)
            return None, None

        # Handle filters
        if line.startswith("[+]"):
            keyword = line[3:].strip()
            filters.add_must_contain(keyword)
            return None, None
        elif line.startswith("[-]"):
            path_or_keyword = line[3:].strip()
            if os.path.isabs(path_or_keyword):
                if os.path.isfile(path_or_keyword):
                    filters.add_ignored_file(path_or_keyword)
                else:
                    filters.add_ignored_dir(path_or_keyword)
            else:
                filters.add_must_not_contain(path_or_keyword)
            return None, None

        # Initialize default modifiers
        weight_modifier = 100
        proportion = None
        is_percentage = True
        graft_level = None
        group = None
        mode = defaults.mode
        mode_modifier = None
        depth = defaults.depth
        flat = False
        video = None
        mute = None

        # Extract all modifiers
        modifiers = modifier_pattern.findall(line)
        # Remove all modifiers from the line to get the path
        path = modifier_pattern.sub("", line).strip()

        # Process each modifier
        for mod in modifiers:
            mod_content = mod.strip("[]").strip()
            if weight_modifier_pattern.match(mod_content):
                # Weight modifier
                if mod_content.endswith("%"):
                    weight_modifier = int(mod_content[:-1])
                    is_percentage = True
                else:
                    weight_modifier = int(mod_content)
                    is_percentage = False
            elif proportion_pattern.match(mod_content):
                # Proportion
                proportion = int(mod_content[1:-1])
            elif graft_pattern.match(mod_content):
                # Graft level modifier
                graft_level = int(mod_content[1:])
            elif group_pattern.match(mod_content):
                # Group
                group = mod_content[1:]
            elif mode_pattern.match(mod_content):
                # Balance level modifier, global only
                mode_modifier = parse_mode_string(mod_content)
            elif depth_pattern.match(mod_content):
                # Depth modifier
                depth = int(mod_content[1:])
            elif flat_pattern.match(mod_content):
                flat = True
            elif video_pattern.match(mod_content):
                # Video modifier
                video = True
            elif no_video_pattern.match(mod_content):
                video = False
            elif mute_pattern.match(mod_content):
                mute = True
            elif no_mute_pattern.match(mod_content):
                mute = False
            else:
                print(f"Unknown modifier '{mod_content}' in line: {line}")
            # Handle directory or specific image
        if path == "*":
            if group:
                defaults.groups[group] = {
                    "proportion": proportion or None,
                    "graft_level": graft_level or None,
                    "mode_modifier": mode_modifier or (),
                }
                return None, None
            if video is not None or mute is not None:
                defaults.set_global_video(video=video, mute=mute)
            if recdepth == 1:
                defaults.set_global_defaults(mode=mode_modifier or mode, depth=depth)
            return None, None

        if os.path.isdir(path):
            return path, {
                "weight_modifier": weight_modifier,
                "is_percentage": is_percentage,
                "proportion": proportion,
                "graft_level": graft_level,
                "group": group,
                "mode_modifier": mode_modifier,
                "depth": depth,
                "flat": flat,
                "video": video,
            }
        elif os.path.isfile(path):
            return path, {
                "weight_modifier": weight_modifier,
                "is_percentage": is_percentage,
                "proportion": proportion,
                "graft_level": graft_level,
                "group": group,
                "mode_modifier": mode_modifier,
            }
        else:
            print(f"Path '{path}' is neither a file nor a directory.")

        return None, None

    def process_entry(entry):
        """
        Process a single input entry (file, directory, or image).
        """
        nonlocal image_dirs, specific_images

        additional_search_paths = [os.path.dirname(entry)]
        input_filename_full = find_input_file(entry, additional_search_paths)

        if input_filename_full:
            match os.path.splitext(input_filename_full)[1].lower():
                case ".lst":
                    with open(
                        input_filename_full, "r", buffering=65536, encoding="utf-8"
                    ) as f:
                        total_lines = sum(1 for _ in f)
                        f.seek(0)
                        for line in tqdm(
                            f,
                            desc=f"Parsing {input_filename_full}",
                            unit="line",
                            total=total_lines,
                            disable=args.quiet,
                        ):
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            image_path, weight_str = line.rsplit(",", 1)  # Split on last comma
                            if weight_str:  # Expecting "image_path,weight"
                                try:
                                    weights.append(float(weight_str))
                                    all_images.append(image_path)
                                except ValueError:
                                    # weight_str is not a number, so it's part of the image path (comma in filename)
                                    all_images.append(f"{image_path},{weight_str}")
                                    weights.append(0.01)  # Default weight for single lines
                            else:  # Probably an irfanview-style list
                                all_images.append(line)
                                weights.append(0.01)  # Default weight for single lines
                case ".txt":
                    with open(
                        input_filename_full, "r", buffering=65536, encoding="utf-8"
                    ) as f:
                        total_lines = sum(1 for _ in f)
                        f.seek(0)
                        for line in tqdm(
                            f,
                            desc=f"Parsing {input_filename_full}",
                            unit="line",
                            total=total_lines,
                            disable=args.quiet,
                        ):
                            line = line.strip()
                            if not line or line.startswith(
                                "#"
                            ):  # Skip comments/empty lines
                                continue
                            line = line.replace(
                                '"', ""
                            ).strip()  # Remove enclosing quotes

                            if utils.is_textfile(
                                line
                            ):  # Recursively process nested text files
                                sub_image_dirs, sub_specific_images = (
                                    process_inputs([line], defaults, recdepth + 1)
                                )
                                image_dirs.update(sub_image_dirs)
                                specific_images.update(sub_specific_images)
                            else:
                                path, modifier_list = parse_input_line(
                                    line, defaults, recdepth
                                )
                                if modifier_list:
                                    if utils.is_imagefile(path):
                                        specific_images[path] = modifier_list
                                    else:
                                        image_dirs[path] = modifier_list
        else:  # Handle directories and images directly
            path, modifier_list = parse_input_line(entry, defaults, recdepth)
            if modifier_list:
                if utils.is_imagefile(path):
                    specific_images[path] = modifier_list
                else:
                    image_dirs[path] = modifier_list

    # Process each entry in the input list
    for input_entry in input_files:
        process_entry(input_entry)

    return image_dirs, specific_images, all_images, weights

def start_slideshow(all_image_paths, weights, defaults):
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
    slideshow = ImageSlideshow(root, all_image_paths, weights, defaults, filters, args.quiet)  # noqa: F841
    root.mainloop()

def main(input_files, defaults, test_iterations=None, testdepth=None, printtree=None):
    # Parse input files and directories
    image_dirs, specific_images, all_images, weights = process_inputs(
        input_files, defaults
    )

    if not any([image_dirs, specific_images, all_images, weights]):
        raise ValueError("No images found in the provided input files.")

    if image_dirs or specific_images:
        # Instantiate and build the tree
        tree = Tree()
        tree.build_tree(image_dirs, specific_images, defaults, filters)
        tree.calculate_weights(defaults=defaults)

        # Print tree if requested
        if printtree:
            tree.print_tree(defaults, max_depth=testdepth)
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
        start_slideshow(all_images, weights, defaults)

if __name__ == "__main__":
    defaults = Defaults(args=args)
    filters = Filters()

    # Use args.input_file directly as a list
    input_files = args.input_file if args.input_file else []

    if args.run or args.output:
        main(input_files, defaults)
    elif args.printtree:
        main(input_files, defaults, testdepth=args.testdepth, printtree=True)
    elif args.test:
        main(
            input_files,
            defaults,
            test_iterations=args.test,
            testdepth=args.testdepth if args.testdepth else defaults.depth + 1,
        )
