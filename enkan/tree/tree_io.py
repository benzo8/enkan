import os
import logging
from datetime import datetime
from typing import Sequence
from enkan.tree.Tree import Tree


logger = logging.getLogger(__name__)


class _LegacyDefaults:
    """
    Compatibility stand-in for old pickles that stored enkan.utils.Defaults.

    This is only used during unpickling; new trees store BuildState directly.
    """

    @property
    def mode(self):
        args_mode = getattr(self, "args_mode", None)
        if args_mode is not None:
            return args_mode
        global_mode = getattr(self, "global_mode", None)
        if global_mode is not None:
            return global_mode
        return getattr(self, "_mode", None)


class _LegacyTreeUnpickler:
    def __init__(self, file_obj):
        import pickle

        class _Unpickler(pickle.Unpickler):
            def find_class(self, module, name):
                if module == "enkan.utils.Defaults" and name == "Defaults":
                    return _LegacyDefaults
                return super().find_class(module, name)

        self._unpickler = _Unpickler(file_obj)

    def load(self):
        return self._unpickler.load()


def load_tree_if_current(filename: str) -> Tree | None:
    """
    Attempt to load a pickled Tree, rebuild derived indexes in memory, and
    return None only when the tree cannot be prepared for runtime use.
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
    try:
        tree.rebuild_indexes()
        tree.build_runtime_resolution_indexes()
        tree._pickle_version = Tree.PICKLE_VERSION
    except Exception as exc:
        tree_filename = os.path.basename(filename)
        txt_filename = os.path.splitext(tree_filename)[0] + ".txt"
        logger.info(
            "[tree] '%s' could not be prepared for runtime use "
            "(pickle_version=%s, required=%d, error=%s).\n"
            "Please rebuild with: enkan --input_file %s --outputtree",
            tree_filename,
            version_in_pickle,
            Tree.PICKLE_VERSION,
            exc,
            txt_filename,
        )
        return None

    if version_in_pickle is None or version_in_pickle < Tree.PICKLE_VERSION:
        logger.info(
            "[tree] Repaired outdated tree '%s' in memory "
            "(pickle_version=%s, required=%d).",
            os.path.basename(filename),
            version_in_pickle,
            Tree.PICKLE_VERSION,
        )
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
    with open(input_path, "rb") as f:
        return _LegacyTreeUnpickler(f).load()


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
