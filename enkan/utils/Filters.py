import os
from dataclasses import dataclass
from itertools import accumulate

from enkan.tree.selection_scope import SelectionScope, SelectionUnit
from enkan.utils import utils


class BuildFilters:
    def __init__(self, *, dont_recurse: bool = False, include_video: bool = True):
        self.must_contain = set()
        self.must_not_contain = set()
        self.ignored_dirs = set()
        self.ignored_files = set()
        self.ignored_files_dirs = set()
        self.dont_recurse = dont_recurse
        self.dont_recurse_beyond = set()
        self.include_video = include_video

    def clone_for_source(self) -> "BuildFilters":
        """
        Create a source-local clone for input parsing/building.

        This preserves top-level filter state while isolating per-source filter
        mutations such as txt-local include/exclude directives.
        """
        clone = BuildFilters(
            dont_recurse=self.dont_recurse,
            include_video=self.include_video,
        )
        clone.must_contain = set(self.must_contain)
        clone.must_not_contain = set(self.must_not_contain)
        clone.ignored_dirs = set(self.ignored_dirs)
        clone.ignored_files = set(self.ignored_files)
        clone.ignored_files_dirs = set(self.ignored_files_dirs)
        clone.dont_recurse_beyond = set(self.dont_recurse_beyond)
        return clone

    def preprocess_ignored_files(self):
        for ignored in self.ignored_files:
            dir_path = os.path.dirname(ignored)
            self.ignored_files_dirs.add(dir_path)

    def add_must_contain(self, keyword):
        self.must_contain.add(keyword)

    def add_must_not_contain(self, keyword):
        self.must_not_contain.add(keyword)

    def add_ignored_dir(self, directory):
        self.ignored_dirs.add(directory)

    def add_ignored_file(self, file):
        self.ignored_files.add(file)

    def add_dont_recurse_beyond_folder(self, folder):
        self.dont_recurse_beyond.add(folder)

    def passes(self, path):
        if any(
            os.path.normpath(path) == os.path.normpath(ignored_dir)
            for ignored_dir in self.ignored_dirs
        ):
            return 1

        if any(keyword in path for keyword in self.must_not_contain):
            return 2

        if self.must_contain and not any(
            keyword in path for keyword in self.must_contain
        ):
            return 2

        if any(
            os.path.normpath(path) == os.path.normpath(dont_recurse_beyond_dir)
            for dont_recurse_beyond_dir in self.dont_recurse_beyond
        ):
            return 3

        return 0


@dataclass(frozen=True)
class RuntimeFilters:
    include_video: bool = True

    def apply_to_selection_scope(self, selection_scope: SelectionScope) -> SelectionScope:
        if self.include_video:
            return selection_scope

        image_paths: list[str] = []
        weights: list[float] = []
        selection_units: list[SelectionUnit] = []

        for unit in selection_scope.selection_units:
            unit_images: list[str] = []
            unit_weights: list[float] = []
            start_index = len(image_paths)
            for image_path, weight in zip(unit.image_paths, unit.weights):
                if utils.is_videofile(image_path):
                    continue
                image_paths.append(image_path)
                weights.append(weight)
                unit_images.append(image_path)
                unit_weights.append(weight)
            if unit_images:
                selection_units.append(
                    SelectionUnit(
                        node_key=unit.node_key,
                        node_level=unit.node_level,
                        ancestor_keys=unit.ancestor_keys,
                        image_paths=unit_images,
                        weights=unit_weights,
                        cum_weights=list(accumulate(unit_weights)),
                        base_total=sum(unit_weights),
                        start_index=start_index,
                    )
                )

        if not selection_scope.selection_units:
            for image_path, weight in zip(selection_scope.image_paths, selection_scope.weights):
                if utils.is_videofile(image_path):
                    continue
                image_paths.append(image_path)
                weights.append(weight)

        return SelectionScope.from_parts(
            image_paths,
            weights,
            selection_units,
        )


Filters = BuildFilters
