from __future__ import annotations

import os
import bisect
import random
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence, List, Set, Optional, TYPE_CHECKING

from enkan import constants


if TYPE_CHECKING:
    from enkan.tree.Tree import Tree
    from enkan.utils.Filters import Filters

def weighted_choice(image_paths: Sequence[str], cum_weights: Sequence[float]) -> str:
    """
    Choose an image path according to cumulative weights.

    Args:
        image_paths: Sequence of items (must align with cum_weights length).
        cum_weights: Monotonically non‑decreasing cumulative totals.

    Returns:
        Selected image path.

    Raises:
        ValueError: If inputs are empty or lengths mismatch.
    """
    if not image_paths or not cum_weights:
        raise ValueError("weighted_choice received empty inputs")
    if len(image_paths) != len(cum_weights):
        raise ValueError("image_paths and cum_weights length mismatch")
    total = cum_weights[-1]
    if total <= 0:
        raise ValueError("Total cumulative weight must be > 0")
    x = random.random() * total  # marginally cheaper than uniform(0, total)
    idx = bisect.bisect_left(cum_weights, x)
    # Clamp (in pathological float edge)
    if idx >= len(image_paths):
        idx = len(image_paths) - 1
    return image_paths[idx]


def level_of(path: str) -> int:
    """
    Count path components (ignoring empty segments).

    Args:
        path: Filesystem path.

    Returns:
        Number of non‑empty components.
    """
    return sum(1 for part in path.split(os.sep) if part)


def truncate_path(path: str, levels_up: int) -> str:
    """
    Truncate a path to a certain depth.

    Args:
        path: Original path.
        levels_up:
            If >= 0: keep only the first 'levels_up' components.
            If <  0: remove 'levels_up' components from the end (negative trim).

    Returns:
        Truncated path string (components rejoined with backslash).
    """
    parts = [p for p in path.split("\\") if p]
    if levels_up < 0:
        keep = len(parts) + levels_up  # levels_up negative
        if keep < 0:
            keep = 0
        parts = parts[:keep]
    else:
        parts = parts[:levels_up]
    return "\\".join(parts)


def get_drive_or_root(path: str) -> str:
    """
    Extract drive root (Windows) or root slash (Unix).

    Args:
        path: Path string.

    Returns:
        'C:\\' style drive root, '/' for POSIX absolute, or '' for relative paths.
    """
    drive, _ = os.path.splitdrive(path)
    if drive:
        return drive + os.path.sep
    if path.startswith(os.path.sep):
        return os.path.sep
    return ""


def contains_subdirectory(path: str) -> int | bool:
    """
    Determine if a directory contains (at least one) subdirectory.

    Args:
        path: Directory path.

    Returns:
        Number of immediate child directories (truthy count) or False if none / path invalid.
    """
    try:
        with os.scandir(path) as it:
            dirs = [e for e in it if e.is_dir()]
        return len(dirs) if dirs else False
    except OSError:
        return False


def contains_files(path: str) -> bool:
    """
    Quickly test if any file exists somewhere under path.

    Args:
        path: Directory path.

    Returns:
        True if at least one file found, else False.
    """
    try:
        for root, _, files in os.walk(path):
            if files:
                return True
        return False
    except OSError:
        return False


def is_textfile(file: str) -> bool:
    """Return True if filename has a text extension."""
    return file.lower().endswith(constants.TEXT_FILES)


def is_imagefile(file: str) -> bool:
    """Return True if filename has an image extension."""
    return file.lower().endswith(constants.IMAGE_FILES)


def is_videofile(file: str) -> bool:
    """Return True if filename has a video extension."""
    return file.lower().endswith(constants.VIDEO_FILES)


def is_videoallowed(data_video: bool | None, defaults) -> bool:
    """
    Determine if video inclusion is allowed for a node.

    Precedence:
        1. defaults.args_video (explicit CLI override)
        2. data_video (per node specification)
        3. defaults.video (global default)
    """
    if data_video is False:
        return False
    if getattr(defaults, "args_video", None) is not None:
        return defaults.args_video
    return data_video if data_video is not None else defaults.video


def filter_valid_files(
    path: str,
    files: Sequence[str],
    ignored_files: Iterable[str],
    video_allowed: bool | None = None,
) -> List[str]:
    """
    Filter a directory listing for valid image/video files, excluding ignored files.

    Args:
        path: Directory path.
        files: Filenames in the directory.
        ignored_files: Iterable of full paths to ignore.
        video_allowed: Whether videos may be included (pre-filtered).

    Returns:
        List of full paths (image/video only).
    """
    ignored_set: Set[str] = set(ignored_files)
    # If many files per directory & large ignored_set, this is fine O(n).
    out: List[str] = []
    join = os.path.join
    for f in files:
        full = join(path, f)
        if full in ignored_set:
            continue
        if is_imagefile(f) or (video_allowed and is_videofile(f)):
            out.append(full)
    return out


def filtered_images_from_disk(
    path: str,
    *,
    include_video: bool = False,
    filters: "Filters" | None = None,
    ignored_files: Iterable[str] | None = None,
) -> List[str]:
    """Return the filtered media files that exist directly under ``path``."""
    candidates: List[str] = []
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_file():
                    candidates.append(entry.name)
    except OSError:
        return []

    if ignored_files is not None:
        effective_ignored = list(ignored_files)
    elif filters is not None:
        effective_ignored = list(getattr(filters, 'ignored_files', []))
    else:
        effective_ignored = []

    return filter_valid_files(path, candidates, effective_ignored, include_video)


def images_from_path(
    path: str,
    *,
    tree: "Tree" | None = None,
    include_video: bool = False,
    filters: "Filters" | None = None,
    ignored_files: Iterable[str] | None = None,
) -> List[str]:
    """Lookup images for ``path`` via tree cache; fall back to disk scan."""
    if tree is not None:
        lookup = getattr(tree, 'path_lookup', None)
        if lookup is not None:
            node = lookup.get(path) or lookup.get(os.path.normpath(path))
            if node is not None:
                node_images = getattr(node, 'images', None)
                if node_images:
                    return list(node_images)

    return filtered_images_from_disk(
        path,
        include_video=include_video,
        filters=filters,
        ignored_files=ignored_files,
    )

def find_input_file(
    input_filename: str,
    additional_search_paths: Sequence[str] | None = None,
) -> Optional[str]:
    """
    Locate an input file (.tree / .lst / .txt) by searching common locations.

    Args:
        input_filename: Base filename or explicit file (with or without extension).
        additional_search_paths: Extra directories to search (before the fixed 'lists' dir).

    Returns:
        Absolute path string if found, else None.
    """
    add_paths: List[str] = list(additional_search_paths or [])
    script_dir: Path = Path(__file__).resolve().parent
    cwd: Path = Path.cwd()

    possible_locations: List[Path] = [script_dir, cwd, *map(Path, add_paths), cwd / "lists"]

    base = Path(input_filename)
    ext: str = base.suffix.lower()
    if not ext:
        candidates: List[Path] = [base.with_suffix(".tree"), base.with_suffix(".lst"), base.with_suffix(".txt")]
    else:
        candidates = [base]

    for location in possible_locations:
        for cand in candidates:
            candidate_path: Path = location / cand
            if candidate_path.is_file():
                return str(candidate_path)
    return None


def write_image_list(
    all_images: Sequence[str],
    weights: Sequence[float],
    input_files: Sequence[str],
    mode_args: dict | str,
    output_path: str | os.PathLike[str],
) -> None:
    """
    Write image paths and their weights to a CSV-like text file.

    Args:
        all_images: Sequence of image paths.
        weights: Parallel sequence of weights.
        input_files: Source list filenames.
        mode_args: Mode parameters (serialized or dict).
        output_path: Destination filepath.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = (
        f"# Written: {now}\n"
        f"# Input files: {', '.join(input_files)}\n"
        f"# Mode arguments: {mode_args}\n"
        "# Format: image_path,weight\n"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        for img, w in zip(all_images, weights):
            f.write(f"{img},{w}\n")


def write_tree_to_file(tree, output_path: str | os.PathLike[str]) -> None:
    """
    Pickle (serialize) a Tree object to disk.

    Args:
        tree: The Tree instance.
        output_path: Destination file path.
    """
    import pickle
    with open(output_path, "wb") as f:
        pickle.dump(tree, f, protocol=pickle.HIGHEST_PROTOCOL)


def load_tree_from_file(input_path: str | os.PathLike[str]):
    """
    Load a pickled Tree from disk.

    Args:
        input_path: Path to .tree pickle file.

    Returns:
        Unpickled object (expected Tree).
    """
    import pickle
    with open(input_path, "rb") as f:
        return pickle.load(f)