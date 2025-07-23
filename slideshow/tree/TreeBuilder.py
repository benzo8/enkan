import os

from tqdm import tqdm

import slideshow.utils.utils as utils

class TreeBuilder:
    def __init__(self, tree):
        self.tree = tree

    def build_tree(self, image_dirs, specific_images, quiet=False):
        """
        Read image_dirs and specific_images and build a tree.
        """
        # Initialize tqdm progress bar
        with tqdm(total=0, desc="Building tree", unit="file", disable=quiet) as pbar:
            for root, data in image_dirs.items():

                if not self.tree.find_node(root, lookup_dict=self.tree.path_lookup):

                    if data.get("flat", False):
                        self.add_flat_branch(root, data, pbar)
                    else:
                        # Process each directory
                        self.process_directory(root, data, pbar)

                # Insert proportion & mode if specified
                if root in image_dirs:
                    if (
                        data.get("proportion") is not None
                        or data.get("mode_modifier") is not None
                    ):
                        # If a proportion is specified, use it
                        self.tree.append_overwrite_or_update(
                            root,
                            data.get("level", self.tree.calculate_level(root)),
                            {
                                "weight_modifier": data.get("weight_modifier", 100),
                                "is_percentage": data.get("is_percentage", True),
                                "proportion": data.get("proportion"),
                                "mode_modifier": data.get("mode_modifier"),
                                "images": [],
                            },
                        )

                self.tree.handle_grafting(
                    root, data.get("graft_level"), data.get("group")
                )

        # Handle specific images if provided
        if specific_images:
            self.process_specific_images(specific_images)

    def process_directory(self, root, data, pbar):
        """
        Process a single root directory and add nodes to the tree.
        Handles image processing and grafting.
        """
        root_level = utils.level_of(root)

        # Traverse the directory tree
        for path, dirs, files in os.walk(root):
            if self.tree.filters.passes(path) == 0:
                # Update the total for new files discovered
                pbar.total += len(files)
                pbar.desc = f"Processing {path}"
                pbar.update(len(files))
                pbar.refresh()
                self.process_path(path, files, dirs, data, root_level)
            elif self.tree.filters.passes(path) == 1:
                del dirs[:]  # Prune directories

    def process_path(self, path, files, dirs, data, root_level):
        """
        Process an individual path, adding images or virtual nodes as needed.
        """
        images = utils.filter_valid_files(
            path,
            files,
            self.tree.filters.ignored_files,
            utils.is_videoallowed(data.get("video"), self.tree.defaults),
        )
        path_level = self.tree.calculate_level(path)

        if dirs and images:
            # Create a special "images" branch for directories with images
            self.add_images_branch(path, images, path_level + 1, data)
        else:
            # Add a regular branch
            self.add_regular_branch(path, images, path_level, data)

    def add_flat_branch(self, path, data, pbar):
        """
        Add a special 'flat' branch for directories with images.
        """

        def flatten_branch(root):
            """
            Collect all images from the branch rooted at `root`, including subdirectories.

            Args:
                root (str): The root directory of the branch.

            Returns:
                list: A list of full paths to all images in the branch.
            """
            images = []
            for path, _, files in os.walk(root):
                images.extend(
                    os.path.join(path, f)
                    for f in files
                    if utils.is_imagefile(f)
                    or (
                        utils.is_videofile(f)
                        and utils.is_videoallowed(data.get("video"), self.tree.defaults)
                    )
                )
            return images

        pbar.desc = f"Flattening {path}"
        pbar.refresh()

        images = flatten_branch(path)
        level = data.get("level", self.tree.calculate_level(path))

        pbar.total += len(images)
        pbar.update(len(images))
        pbar.refresh()

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

    def add_images_branch(self, path, images, level, data):
        """
        Add a special 'images' branch for directories with images.
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


    def add_regular_branch(self, path, images, level, data):
        """
        Add a regular branch for paths that don't need truncation.
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

    def process_specific_images(self, specific_images):
        """
        Process specific images and add them to the tree.
        """
        num_average_images = int((lambda a, b: b / a)(*self.tree.count_branches(self.tree.root)))

        for path, data in specific_images.items():
            if self.tree.filters.passes(path) == 0:
                node_name = path
                is_percentage = data.get("is_percentage", True)
                level = data.get("level", self.tree.calculate_level(node_name))

                self.tree.append_overwrite_or_update(
                    node_name,
                    level,
                    {
                        "weight_modifier": data.get("weight_modifier", 100),
                        "is_percentage": is_percentage,
                        "proportion": data.get("proportion", None),
                        "mode_modifier": data.get("mode_modifier", None),
                        "images": [path]
                        * (
                            num_average_images
                            if is_percentage
                            else data.get("weight_modifier", 100)
                        ),
                    },
                )

                # Handle grafting after processing the directory
                graft_level = data.get("graft_level") or level
                group = data.get("group")
                self.tree.handle_grafting(node_name, graft_level, group)
