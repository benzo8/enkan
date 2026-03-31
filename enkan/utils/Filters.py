import os

class Filters:
    def __init__(self):
        self.must_contain = set()
        self.must_not_contain = set()
        self.ignored_dirs = set()
        self.ignored_files = set()
        self.ignored_files_dirs = set()
        self.dont_recurse_beyond = set()

    def clone_for_source(self) -> "Filters":
        """
        Create a source-local clone for input parsing/building.

        This preserves top-level filter state while isolating per-source filter
        mutations such as txt-local include/exclude directives.
        """
        clone = Filters()
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
