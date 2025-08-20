from __future__ import annotations

import os
from typing import Dict, List, Mapping, Optional

from tqdm import tqdm

import slideshow.utils.utils as utils
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
                # Skip nonexistent roots early (helps catch typos)
                if not os.path.isdir(root):
                    # (Optional: emit a warning via utils.log if you have one)
                    continue

                # Only construct branch structure if not already present
                if not self.tree.find_node(root, lookup_dict=self.tree.path_lookup):
                    if data.get("flat", False):
                        self.add_flat_branch(root, data, pbar)
                    else:
                        self.process_directory(root, data, pbar)
                else:
                    # Ensure the is updated with current metadata
                    self.tree.append_overwrite_or_update(
                        root,
                        data.get("level", self.tree.calculate_level(root)),
                        {
                            "weight_modifier": data.get("weight_modifier", 100),
                            "is_percentage": data.get("is_percentage", True),
                            "proportion": data.get("proportion"),
                            "mode_modifier": data.get("mode_modifier"),
                            "images": [],  # directory node itself holds no direct images here
                        },
                    )

                # Grafting (after node exists)
                self.grafting.handle_grafting(
                    root,
                    data.get("graft_level"),
                    data.get("group"),
                )

        if specific_images:
            self.process_specific_images(specific_images)

    def process_directory(
        self,
        root: str,
        data: ImageDirConfig,
        pbar: tqdm,
    ) -> None:
        """
        Walk a root directory, adding nodes (regular or 'images' sub-branches).
        """
        root_level = utils.level_of(root)
        filters = self.tree.filters

        for path, dirs, files in os.walk(root, topdown=True):
            result = filters.passes(path)
            if result in (0, 3):
                # Treat discovered files as processed for progress
                file_count = len(files)
                if file_count:
                    pbar.total += file_count
                    pbar.desc = f"Processing {path}"
                    pbar.update(file_count)
                    pbar.refresh()
                self.process_path(path, files, dirs, data, root_level)
            # Prune (stop descending) if result is 1 or 3 OR global dont_recurse
            if result in (1, 3) or self.tree.defaults.dont_recurse:
                del dirs[:]  # modifies in-place

    def process_path(
        self,
        path: str,
        files: List[str],
        dirs: List[str],
        data: ImageDirConfig,
        root_level: int,
    ) -> None:
        """
        For a given filesystem path, decide how to add it to the tree depending
        on whether it contains images and subdirectories.
        """
        include_video = utils.is_videoallowed(data.get("video"), self.tree.defaults)
        images = utils.filter_valid_files(
            path,
            files,
            self.tree.filters.ignored_files,
            include_video,
        )
        if not images:
            return

        path_level = self.tree.calculate_level(path)
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
        include_video = utils.is_videoallowed(data.get("video"), self.tree.defaults)

        def collect_images(root_dir: str) -> List[str]:
            images_accum: List[str] = []
            for dir_path, _, files in os.walk(root_dir):
                valid_files = [
                    f
                    for f in files
                    if utils.is_imagefile(f)
                    or (include_video and utils.is_videofile(f))
                ]
                if valid_files:
                    traversed_paths.append(dir_path)
                    count = len(valid_files)
                    pbar.total += count
                    pbar.update(count)
                    pbar.refresh()
                    images_accum.extend(os.path.join(dir_path, f) for f in valid_files)
            return images_accum

        pbar.desc = f"Flattening {path}"
        pbar.refresh()

        images = collect_images(path)
        level = data.get("level", self.tree.calculate_level(path))

        self.tree.append_overwrite_or_update(
            path,
            level,
            {
                "weight_modifier": data.get("weight_modifier", 100),
                "is_percentage": data.get("is_percentage", True),
                "proportion": None,
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
        self.tree.append_overwrite_or_update(
            images_path,
            level,
            {
                "weight_modifier": 100,
                "is_percentage": True,
                "proportion": None,
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
        self.tree.append_overwrite_or_update(
            path,
            level,
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

            self.tree.append_overwrite_or_update(
                node_name,
                level,
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
