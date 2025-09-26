import os
from enkan.utils.utils import level_of
from typing import Mapping, Optional

class Filters:
    def __init__(self):
        self.must_contain = set()
        self.must_not_contain = set()
        self.ignored_dirs = set()
        self.ignored_files = set()
        self.ignored_files_dirs = set()
        self.dont_recurse_beyond = set()
        self.ignore_below_bottom = False
        self.lowest_rung: Optional[int] = None

    def preprocess_ignored_files(self):
        for ignored in self.ignored_files:
            dir_path = os.path.dirname(ignored)
            self.ignored_files_dirs.add(dir_path)

    def configure_ignore_below_bottom(
        self,
        enabled: bool,
        mode: Mapping[int, object] | None = None,
    ) -> None:
        self.ignore_below_bottom = enabled
        if enabled and mode:
            try:
                self.lowest_rung = min(mode.keys())
                pass
            except ValueError:
                self.lowest_rung = None
        else:
            self.lowest_rung = None

    def _should_ignore_below_bottom(self, path: str) -> bool:
        if not self.ignore_below_bottom or self.lowest_rung is None:
            return False
        return level_of(path) < self.lowest_rung

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

        if self._should_ignore_below_bottom(path):
            return 2

        if any(
            os.path.normpath(path) == os.path.normpath(dont_recurse_beyond_dir)
            for dont_recurse_beyond_dir in self.dont_recurse_beyond
        ):
            return 3

        return 0
