from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace

from enkan.utils.Defaults import Defaults
from enkan.utils.Filters import Filters
from enkan.tree.Tree import Tree
from enkan.utils.input.input_models import SourceKind, LoadedSource, should_bypass_merge
from enkan.utils.input.TreeMerger import TreeMerger


class BypassDetectionTests(unittest.TestCase):
    def test_single_txt_without_nested_bypasses(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("C:/images\n")
            path = f.name
        try:
            self.assertTrue(should_bypass_merge([path]))
        finally:
            os.unlink(path)

    def test_single_txt_with_nested_requires_merge(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("other.txt\n")
            path = f.name
        try:
            self.assertFalse(should_bypass_merge([path]))
        finally:
            os.unlink(path)

    def test_single_lst_requires_merge(self):
        with tempfile.NamedTemporaryFile("w", suffix=".lst", delete=False) as f:
            f.write("C:/images/foo.jpg,1\n")
            path = f.name
        try:
            self.assertFalse(should_bypass_merge([path]))
        finally:
            os.unlink(path)


class TreeMergerTests(unittest.TestCase):
    def setUp(self):
        self.defaults = Defaults(
            args=SimpleNamespace(
                mode=None,
                random=None,
                dont_recurse=None,
                video=None,
                mute=None,
                debug=False,
                no_background=False,
            )
        )
        self.filters = Filters()

    def _make_tree(self, path: str, images) -> Tree:
        tree = Tree(self.defaults, self.filters)
        try:
            tree.ensure_parent_exists(os.path.dirname(path))
        except ValueError:
            pass
        tree.create_node(
            path,
            {
                "weight_modifier": 100,
                "is_percentage": True,
                "proportion": 100,
                "mode_modifier": None,
                "images": list(images),
            },
        )
        return tree

    def test_merge_appends_missing_images(self):
        base = self._make_tree(r"C:\foo", ["a.jpg"])
        incoming = self._make_tree(r"C:\foo", ["b.jpg"])

        merger = TreeMerger()
        result = merger.merge(
            [
                LoadedSource("base", SourceKind.TREE, 0, tree=base),
                LoadedSource("incoming", SourceKind.TREE, 1, tree=incoming),
            ]
        )
        merged_images = result.tree.path_lookup[os.path.normpath(r"C:\foo")].images
        self.assertIn("a.jpg", merged_images)
        self.assertIn("b.jpg", merged_images)

    def test_merge_adds_new_branch(self):
        base = self._make_tree(r"C:\foo", ["a.jpg"])
        incoming = self._make_tree(r"C:\bar", ["x.jpg"])
        merger = TreeMerger()
        result = merger.merge(
            [
                LoadedSource("base", SourceKind.TREE, 0, tree=base),
                LoadedSource("incoming", SourceKind.TREE, 1, tree=incoming),
            ]
        )
        self.assertIn(os.path.normpath(r"C:\bar"), result.tree.path_lookup)

    def test_merge_preserves_existing_proportion(self):
        base = self._make_tree(r"C:\foo", ["a.jpg"])
        base_node = base.path_lookup[os.path.normpath(r"C:\foo")]
        base_node.proportion = 25
        base_node.user_proportion = 25

        incoming = self._make_tree(r"C:\foo", ["b.jpg"])
        incoming_node = incoming.path_lookup[os.path.normpath(r"C:\foo")]
        incoming_node.proportion = 75
        incoming_node.user_proportion = 75

        merger = TreeMerger()
        result = merger.merge(
            [
                LoadedSource("base", SourceKind.TREE, 0, tree=base),
                LoadedSource("incoming", SourceKind.TREE, 1, tree=incoming),
            ]
        )

        merged_node = result.tree.path_lookup[os.path.normpath(r"C:\foo")]
        # Existing proportion/user_proportion should remain unchanged
        self.assertEqual(merged_node.proportion, 25)
        self.assertEqual(getattr(merged_node, "user_proportion", None), 25)


if __name__ == "__main__":
    unittest.main()
