import os
import re
from tqdm import tqdm

from slideshow import constants
from slideshow.utils import utils
from slideshow.utils.Defaults import parse_mode_string

def process_inputs(input_files, defaults, filters, quiet=False, recdepth=1):
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

    def parse_input_line(line, defaults, filters, recdepth):
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

    def process_entry(entry, defaults, filters, quiet=False):
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
                            disable=quiet,
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
                            disable=quiet,
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
                                    line, defaults, filters, recdepth
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
        process_entry(input_entry, defaults, filters, quiet)

    return image_dirs, specific_images, all_images, weights