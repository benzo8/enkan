from __future__ import annotations

import os
from typing import Dict, List, Mapping, Optional, Literal

from tqdm import tqdm

from enkan.tree.TreeNode import TreeNode
from enkan.utils.Filters import Filters
import enkan.utils.utils as utils
from .Tree import Tree
from .Grafting import Grafting

ImageDirConfig = Dict[str, object]
SpecificImagesConfig = Dict[str, Dict[str, object]]


class TreeBuilder:
    def __init__(self, tree: Tree) -> None:
        """
        Parameters:
            tree: The Tree instance to populate.
        """
        self.tree: Tree = tree
        self.grafting: Grafting = Grafting(self.tree)

    def build_tree(
        self,
        image_dirs: Mapping[str, ImageDirConfig],
        specific_images: Optional[SpecificImagesConfig],
        quiet: bool = False,
    ) -> None:
        """
        Build the tree from a mapping of root directories (image_dirs) and an optional
        mapping of specific (virtual) image entries.

        image_dirs structure (per root):
            {
              "weight_modifier": int,
              "is_percentage": bool,
              "proportion": float|None,
              "mode_modifier": any,
              "flat": bool,
              "video": bool|None,
              "level": int|None,
              "graft_level": int|None,
              "group": str|None
            }
        """
        if not image_dirs and not specific_images:
            return

        with tqdm(
            total=0,
            desc="Building tree",
            unit="file",
            disable=quiet,
            dynamic_ncols=True,
            leave=False,
        ) as pbar:
            for root, data in image_dirs.items():
                if not os.path.isdir(root):
                    continue

                # 1. Ensure a structural node exists up-front so metadata (proportion, weight_modifier, etc.)
                #    is not lost if the directory itself has zero images.
                self._ensure_structural_root_node(root, data)

                # 2. Populate children / image branches unless flat
                if data.get("flat", False):
                    self.add_flat_branch(root, data, pbar)
                else:
                    self.process_directory(root, data, pbar)

                # 3. Grafting after node exists
                self.grafting.handle_grafting(
                    root,
                    data.get("graft_level"),
                    data.get("group"),
                )

        if specific_images:
            self.process_specific_images(specific_images)

    # --- new helper ----------------------------------------------------------

    def _ensure_structural_root_node(self, root: str, data: ImageDirConfig) -> None:
        """
        Create an empty node for the root directory if it does not already exist,
        so that its metadata (weight_modifier / proportion / mode_modifier) participates
        in later weight calculations even if the root has no direct images.
        """
        if root in self.tree.path_lookup:
            return
        self.tree.create_node(
            root,
            {
                "weight_modifier": data.get("weight_modifier", 100),
                "is_percentage": data.get("is_percentage", True),
                "proportion": data.get("proportion", None),
                "mode_modifier": data.get("mode_modifier"),
                "images": [],  # intentionally empty
            },
        )

    def process_directory(
        self,
        root: str,
        data: ImageDirConfig,
        pbar: tqdm,
    ) -> None:
        """
        Walk a root directory, adding nodes (regular or 'images' sub-branches).
        """
        filters: Filters = self.tree.filters

        for path, dirs, files in os.walk(root, topdown=True):
            result: Literal[1] | Literal[2] | Literal[3] | Literal[0] = filters.passes(path)
            if result in (0, 3):
                # Treat discovered files as processed for progress
                file_count: int = len(files)
                if file_count:
                    pbar.total += file_count
                    pbar.desc = f"Processing {path}"
                    pbar.update(file_count)
                    pbar.refresh()
                self.process_path(path, files, dirs, data)
            # Prune (stop descending) if result is 1 or 3 OR global dont_recurse
            if result in (1, 3) or self.tree.defaults.dont_recurse:
                del dirs[:]  # modifies in-place

    def process_path(
        self,
        path: str,
        files: List[str],
        dirs: List[str],
        data: ImageDirConfig,
    ) -> None:
        """
        For a given filesystem path, decide how to add it to the tree depending
        on whether it contains images and subdirectories.
        """
        include_video: bool = utils.is_videoallowed(data.get("video"), self.tree.defaults)
        images: List[str] = utils.filter_valid_files(
            path,
            files,
            self.tree.filters.ignored_files,
            include_video,
        )
        if not images:
            return

        path_level: int = self.tree.calculate_level(path)
        if dirs:
            # Directory with both subdirs and images → special 'images' branch
            self.add_images_branch(path, images, path_level + 1, data)
        else:
            # Terminal (no subdirs) → regular branch
            self.add_regular_branch(path, images, path_level, data)

    def add_flat_branch(
        self,
        path: str,
        data: ImageDirConfig,
        pbar: tqdm,
    ) -> None:
        """
        Flatten a directory tree into one node accumulating all images.
        """
        traversed_paths: List[str] = []
        include_video: bool = utils.is_videoallowed(data.get("video"), self.tree.defaults)

        def collect_images(root_dir: str) -> List[str]:
            images_accum: List[str] = []
            for dir_path, _, files in os.walk(root_dir):
                valid_files: List[str] = [
                    f
                    for f in files
                    if utils.is_imagefile(f)
                    or (include_video and utils.is_videofile(f))
                ]
                if valid_files:
                    traversed_paths.append(dir_path)
                    count: int = len(valid_files)
                    pbar.total += count
                    pbar.update(count)
                    pbar.refresh()
                    images_accum.extend(os.path.join(dir_path, f) for f in valid_files)
            return images_accum

        pbar.desc = f"Flattening {path}"
        pbar.refresh()

        images: List[str] = collect_images(path)

        node: TreeNode | None = self.tree.path_lookup.get(path)
        if node:
            # Update existing node (e.g. structural root)
            self.tree.update_node(
                node,
                {
                    "images": images,
                },
            )
        else:
            self.tree.create_node(
                path,
                {
                    "weight_modifier": data.get("weight_modifier", 100),
                    "is_percentage": data.get("is_percentage", True),
                    "proportion": data.get("proportion", None),
                    "mode_modifier": data.get("mode_modifier"),
                    "images": images,
                },
            )

        # Alias every traversed sub-path to the flattened node
        flattened_node = self.tree.path_lookup[path]
        for dir_path in traversed_paths:
            self.tree.path_lookup[dir_path] = flattened_node

    def add_images_branch(
        self,
        path: str,
        images: List[str],
        level: int,
        data: ImageDirConfig,
    ) -> None:
        """
        Create a synthetic 'images' child node under a directory that also has subdirectories.
        """
        images_path = os.path.join(path, "images")
        self.tree.create_node(
            images_path,
            {
                "weight_modifier": 100,
                "is_percentage": True,
                "proportion": data.get("proportion", None),
                "mode_modifier": data.get("mode_modifier"),
                "images": images,
            },
        )

    def add_regular_branch(
        self,
        path: str,
        images: List[str],
        level: int,
        data: ImageDirConfig,
    ) -> None:
        """
        Create/overwrite a normal node that directly holds images.
        """
        node: TreeNode | None = self.tree.path_lookup.get(path)
        if node:
            self.tree.update_node(
                node,
                {
                    "images": images,
                },
            )
        else:
            self.tree.create_node(
                path,
                {
                    "weight_modifier": data.get("weight_modifier", 100),
                    "is_percentage": data.get("is_percentage", True),
                    "proportion": None,
                    "mode_modifier": data.get("mode_modifier"),
                    "images": images,
                },
            )

    def process_specific_images(
        self,
        specific_images: SpecificImagesConfig,
    ) -> None:
        """
        Insert 'virtual' nodes for specific images (each image gets its own node).
        Only per-image mapping is added to virtual_image_lookup to conserve memory.
        """
        branches, images_total = self.tree.count_branches(self.tree.root)
        if branches > 0:
            # Average images per branch (floor)
            num_avg_images = max(1, images_total // branches)
        else:
            num_avg_images = 100  # fallback heuristic

        filters = self.tree.filters
        calc_level = self.tree.calculate_level

        for img_path, data in specific_images.items():
            if filters.passes(img_path) != 0:
                continue

            node_name = os.path.join(
                os.path.dirname(img_path),
                os.path.splitext(os.path.basename(img_path))[0],
            )
            is_percentage = data.get("is_percentage", True)
            level = data.get("level", calc_level(node_name))
            weight_modifier = data.get("weight_modifier", 100)

            # Virtual node images list: repeat image depending on weighting mode
            if is_percentage:
                images_list = [img_path] * num_avg_images
            else:
                images_list = [img_path] * weight_modifier

            self.tree.create_node(
                node_name,
                {
                    "weight_modifier": weight_modifier,
                    "is_percentage": is_percentage,
                    "proportion": data.get("proportion"),
                    "mode_modifier": data.get("mode_modifier"),
                    "images": images_list,
                },
            )

            # Map real image file to its virtual node
            self.tree.virtual_image_lookup[img_path] = self.tree.path_lookup[node_name]

            # Grafting after node is in place
            graft_level = data.get("graft_level") or level
            group = data.get("group")
            self.grafting.handle_grafting(node_name, graft_level, group)
