import os
import bisect
import random
from datetime import datetime

from slideshow import constants

def prepare_cumulative_weights(weights):
    cum_weights = []
    total = 0
    for w in weights:
        total += w
        cum_weights.append(total)
    return cum_weights

def weighted_choice(image_paths, cum_weights):
    x = random.uniform(0, cum_weights[-1])
    idx = bisect.bisect_left(cum_weights, x)
    return image_paths[idx]

def level_of(path):
    return len([item for item in path.split(os.sep) if item != ""])


def truncate_path(path, levels_up):
    """
    Truncate the path based on the balance level.
    """
    return "\\".join(
        path.split("\\")[
            : ((level_of(path) - levels_up) if levels_up < 0 else levels_up)
        ]
    )


def get_drive_or_root(path):
    drive, _ = os.path.splitdrive(path)
    if drive:
        # Windows case, drive letter present
        return drive + os.path.sep  # E.g., 'C:\\'
    else:
        # Unix case
        if path.startswith(os.path.sep):
            return os.path.sep  # Root
        else:
            # Relative path, no explicit root
            return ""


def contains_subdirectory(path):
    for root, directories, files in os.walk(path):
        if directories:
            return len(directories)
    return False


def contains_files(path):
    for root, directories, files in os.walk(path):
        if files:
            return True
    return False


def is_textfile(file):
    return file.lower().endswith(constants.TEXT_FILES)


def is_imagefile(file):
    return file.lower().endswith(constants.IMAGE_FILES)


def is_videofile(file):
    return file.lower().endswith(constants.VIDEO_FILES)


def is_videoallowed(data_video, defaults):
    if data_video is False:
        return False
    if defaults.args_video is not None:
        return defaults.args_video
    else:
        return data_video if data_video is not None else defaults.video
    
def log(message, debug):
    if debug:
        print(f"[DEBUG] {message}")


def filter_valid_files(path, files, ignored_files, is_videoallowed=None):
    if path in {os.path.dirname(f) for f in ignored_files}:
        valid_files = [f for f in files if os.path.join(path, f) not in ignored_files]
    else:
        valid_files = files
    return [
        os.path.join(path, f)
        for f in valid_files
        if is_imagefile(f) or (is_videofile(f) and is_videoallowed)
    ]

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
    _, ext = os.path.splitext(input_filename)
    candidates = [input_filename]
    if not ext:
        candidates = [input_filename + ".lst", input_filename + ".txt"]

    for location in possible_locations:
        for candidate in candidates:
            potential_path = os.path.join(location, candidate)
            if os.path.isfile(potential_path):
                return potential_path

    return None

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
            
def write_tree_to_file(tree, output_path):
    import pickle
    with open(output_path, "wb") as f:
        pickle.dump(tree, f, protocol=pickle.HIGHEST_PROTOCOL)
    
def load_tree_from_file(input_path):
    import pickle
    with open(input_path, "rb") as f:
        return pickle.load(f)