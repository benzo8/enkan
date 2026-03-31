import os
import logging
from datetime import datetime
from typing import Sequence
from enkan.tree.Tree import Tree


logger = logging.getLogger(__name__)


def load_tree_if_current(filename: str) -> Tree | None:
    """
    Attempt to load a pickled Tree; return None if version missing/outdated.
    """
    from enkan.utils.progress import progress

    with progress(
        total=1, desc=f"Loading {os.path.basename(filename)}", leave=True
    ) as pbar:
        try:
            tree = load_tree_from_file(filename)
            pbar.update(1)
        except Exception as e:
            pbar.close()
            logger.warning("[tree] Failed to load '%s': %s.", filename, e)
            return None
    version_in_pickle = getattr(tree, "_pickle_version", None)
    if version_in_pickle is None or version_in_pickle < Tree.PICKLE_VERSION:
        tree_filename = os.path.basename(filename)
        txt_filename = os.path.splitext(tree_filename)[0] + ".txt"
        logger.info(
            "[tree] '%s' outdated (pickle_version=%d, required=%d).\n"
            "Please rebuild with: enkan --input_file %s --outputtree",
            tree_filename,
            version_in_pickle,
            Tree.PICKLE_VERSION,
            txt_filename,
        )
        return None
    return tree


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
