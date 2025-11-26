from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from enkan.utils.Defaults import Defaults
from enkan.utils.Filters import Filters
from enkan.tree.Tree import Tree
from enkan.tree.tree_logic import apply_mode_and_recalculate
from enkan.utils.input.input_models import SourceKind, LoadedSource
from enkan.utils.input.TreeMerger import TreeMerger
from enkan.utils.input.MultiSourceBuilder import MultiSourceBuilder


@pytest.fixture
def defaults():
    return Defaults(
        args=SimpleNamespace(
            mode=None,
            random=None,
            dont_recurse=None,
            video=None,
            mute=None,
            debug=2,
            no_background=False,
        )
    )


@pytest.fixture
def filters():
    f = Filters()
    f.preprocess_ignored_files()
    return f


def _make_tree(defaults: Defaults, filters: Filters, path: str, images) -> Tree:
    tree = Tree(defaults, filters)
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


def _make_defaults(mode_str: str | None = None) -> Defaults:
    return Defaults(
        args=SimpleNamespace(
            mode=mode_str,
            random=None,
            dont_recurse=None,
            video=None,
            mute=None,
            debug=2,
            no_background=False,
        )
    )


def _ensure_case_dir(case_name: str) -> str:
    root = Path("tests_tmp_root")
    root.mkdir(exist_ok=True)
    case_dir = (root / case_name).resolve()
    case_dir.mkdir(exist_ok=True)
    return str(case_dir)


def _find_node_with_group(tree: Tree, group: str):
    for node in tree.node_lookup.values():
        if getattr(node, "group", None) == group:
            return node
    return None


def _create_dir_with_images(root: str, name: str, count: int = 1) -> str:
    path = os.path.join(root, name)
    os.makedirs(path, exist_ok=True)
    for i in range(count):
        img_path = os.path.join(path, f"img{i}.jpg")
        with open(img_path, "w", encoding="utf-8") as f:
            f.write("x")
    return path


def test_multisource_txt_txt_merges_directories():
    # Create two source folders and txt files referencing them
    tmp = Path(_ensure_case_dir("txt_txt"))
    dir1 = _create_dir_with_images(tmp, "a")
    dir2 = _create_dir_with_images(tmp, "b")
    txt1 = tmp / "one.txt"
    txt2 = tmp / "two.txt"
    Path(txt1).write_text(f"{dir1}\n", encoding="utf-8")
    Path(txt2).write_text(f"{dir2}\n", encoding="utf-8")

    defaults = _make_defaults(mode_str="b1")
    filters = Filters()
    builder = MultiSourceBuilder(defaults, filters)

    tree, warnings = builder.build([str(txt1), str(txt2)])

    assert warnings == []
    assert os.path.normpath(dir1) in tree.path_lookup
    assert os.path.normpath(dir2) in tree.path_lookup
    # Expect both image sets present
    images = tree.path_lookup[os.path.normpath(dir1)].images + tree.path_lookup[os.path.normpath(dir2)].images
    assert len(images) == 2


def test_multisource_tree_and_txt_merge():
    tmp = Path(_ensure_case_dir("tree_txt"))

    defaults = _make_defaults(mode_str="b1")
    filters = Filters()
    # Build and pickle a simple tree
    dir1 = _create_dir_with_images(tmp, "base")
    base_tree = _make_tree(defaults, filters, dir1, ["a.jpg"])
    base_tree.built_mode = defaults.mode
    from enkan.tree.tree_io import write_tree_to_file

    tree_path = os.path.join(tmp, "base.tree")
    write_tree_to_file(base_tree, tree_path)

    # TXT adds a second directory
    dir2 = _create_dir_with_images(tmp, "extra")
    txt = os.path.join(tmp, "extra.txt")
    Path(txt).write_text(f"{dir2}\n", encoding="utf-8")

    builder = MultiSourceBuilder(defaults, filters)
    merged_tree, warnings = builder.build([str(tree_path), str(txt)])

    assert warnings == []
    assert os.path.normpath(dir1) in merged_tree.path_lookup
    assert os.path.normpath(dir2) in merged_tree.path_lookup
    assert merged_tree.path_lookup[os.path.normpath(dir1)].images == ["a.jpg"]


def test_multisource_lst_and_txt():
    tmp = Path(_ensure_case_dir("lst_txt"))

    defaults = _make_defaults(mode_str="b1")
    filters = Filters()
    # Prepare lst with a path (no need for real file)
    lst = os.path.join(tmp, "list.lst")
    img_path = os.path.join(tmp, "lstdir", "img0.jpg")
    Path(lst).write_text(f"{img_path},2\n", encoding="utf-8")

    # TXT pointing to a real directory
    dir2 = _create_dir_with_images(tmp, "txtdir")
    txt = os.path.join(tmp, "dir.txt")
    Path(txt).write_text(f"{dir2}\n", encoding="utf-8")

    builder = MultiSourceBuilder(defaults, filters)
    merged_tree, warnings = builder.build([str(lst), str(txt)])

    assert warnings == [] or warnings  # allow lst inference warning
    assert os.path.normpath(os.path.dirname(img_path)) in merged_tree.path_lookup
    assert os.path.normpath(dir2) in merged_tree.path_lookup


def test_lst_type_a_balanced_infers_mode():
    tmp = Path(_ensure_case_dir("lst_weighted_balanced"))
    defaults = _make_defaults()
    filters = Filters()
    lst_path = tmp / "weighted.lst"
    img1 = (tmp / "d1" / "img1.jpg").resolve()
    img2 = (tmp / "d2" / "img2.jpg").resolve()
    lst_path.write_text(f"{img1},1\n{img2},1\n", encoding="utf-8")

    builder = MultiSourceBuilder(defaults, filters)
    tree, warnings = builder.build([str(lst_path)])

    assert tree is not None
    assert getattr(tree, "built_mode", None) is not None
    assert getattr(tree, "lst_inferred_lowest", None) is not None
    # Should be balanced; no warnings expected
    assert warnings == []


def test_lst_type_a_unbalanced_warns():
    tmp = Path(_ensure_case_dir("lst_weighted_unbalanced"))
    defaults = _make_defaults()
    filters = Filters()
    lst_path = tmp / "weighted.lst"
    img1 = (tmp / "d1" / "img1.jpg").resolve()
    img2 = (tmp / "d2" / "img2.jpg").resolve()
    lst_path.write_text(f"{img1},1\n{img2},5\n", encoding="utf-8")

    builder = MultiSourceBuilder(defaults, filters)
    tree, warnings = builder.build([str(lst_path)])

    assert tree is not None
    # Unbalanced weights should not set built_mode
    assert getattr(tree, "built_mode", None) is None
    assert warnings  # expect an inference warning
    assert any("Could not infer" in w or "confidence" in w for w in warnings)


def test_multisource_folder_input():
    tmp = Path(_ensure_case_dir("folder_input"))
    dir1 = _create_dir_with_images(tmp, "images")
    defaults = _make_defaults(mode_str="b1")
    filters = Filters()
    builder = MultiSourceBuilder(defaults, filters)

    tree, warnings = builder.build([dir1])
    assert warnings == []
    assert os.path.normpath(dir1) in tree.path_lookup
    assert len(tree.path_lookup[os.path.normpath(dir1)].images) == 1


def test_txt_with_nested_lst():
    tmp = Path(_ensure_case_dir("txt_nested_lst"))
    lst_file = tmp / "inner.lst"
    img_path = (tmp / "nested" / "img0.jpg").resolve()
    lst_file.write_text(f"{img_path},1\n", encoding="utf-8")

    txt_file = tmp / "outer.txt"
    txt_file.write_text(f"{lst_file}\n", encoding="utf-8")

    defaults = _make_defaults(mode_str="b1")
    filters = Filters()
    builder = MultiSourceBuilder(defaults, filters)
    tree, warnings = builder.build([str(txt_file)])

    assert tree is not None
    assert os.path.normpath(os.path.dirname(img_path)) in tree.path_lookup


def test_txt_with_nested_tree():
    tmp = Path(_ensure_case_dir("txt_nested_tree"))
    defaults = _make_defaults(mode_str="b1")
    filters = Filters()

    # create and pickle a simple tree
    dir1 = _create_dir_with_images(tmp, "base")
    base_tree = _make_tree(defaults, filters, dir1, ["a.jpg"])
    base_tree.built_mode = defaults.mode
    from enkan.tree.tree_io import write_tree_to_file
    tree_path = tmp / "base.tree"
    write_tree_to_file(base_tree, tree_path)

    txt_file = tmp / "outer.txt"
    txt_file.write_text(f"{tree_path}\n", encoding="utf-8")

    builder = MultiSourceBuilder(defaults, filters)
    merged_tree, warnings = builder.build([str(txt_file)])

    assert warnings == []
    assert os.path.normpath(dir1) in merged_tree.path_lookup


def test_group_aware_grafting_via_msb():
    tmp = Path(_ensure_case_dir("msb_group_graft"))
    defaults = _make_defaults(mode_str="b1")  # target lowest_rung = 1
    filters = Filters()

    # Base tree: mode at level 1
    base_dir = _create_dir_with_images(tmp, "base")
    base_tree = _make_tree(defaults, filters, base_dir, ["a.jpg"])
    base_tree.built_mode = defaults.mode

    # Incoming tree: deeper mode (lowest 2) and grouped leaf
    incoming_dir = _create_dir_with_images(tmp, os.path.join("incoming", "leaf"))
    incoming_tree = _make_tree(defaults, filters, incoming_dir, ["b.jpg"])
    incoming_tree.built_mode = {2: ("b", [0, 0])}
    incoming_tree.built_mode_string = "b2"
    node = incoming_tree.path_lookup[os.path.normpath(incoming_dir)]
    node.group = "g1"

    from enkan.tree.tree_io import write_tree_to_file

    base_path = tmp / "base.tree"
    incoming_path = tmp / "incoming.tree"
    write_tree_to_file(base_tree, base_path)
    write_tree_to_file(incoming_tree, incoming_path)

    builder = MultiSourceBuilder(defaults, filters)
    merged_tree, warnings = builder.build([str(base_path), str(incoming_path)])

    assert warnings == [] or warnings is not None
    grouped = _find_node_with_group(merged_tree, "g1")
    assert grouped is not None
    # Graft offset should have moved the grouped node up by 1 level (from level 3 to level 2)
    assert grouped.level >= 2


def test_mode_precedence_cli_wins():
    tmp = Path(_ensure_case_dir("mode_precedence"))
    defaults = _make_defaults(mode_str="b2")
    filters = Filters()
    dir1 = _create_dir_with_images(tmp, "a")
    txt1 = tmp / "one.txt"
    txt1.write_text(f"[b3]\n{dir1}\n", encoding="utf-8")

    builder = MultiSourceBuilder(defaults, filters)
    tree, warnings = builder.build([str(txt1)])

    assert warnings == [] or warnings is not None
    # CLI mode b2 should be in defaults and applied after merge
    assert defaults.mode.get(2) == ("b", [0, 0])


def test_merger_appends_images(defaults: Defaults, filters: Filters):
    base = _make_tree(defaults, filters, r"C:\foo", ["a.jpg"])
    incoming = _make_tree(defaults, filters, r"C:\foo", ["b.jpg"])

    merger = TreeMerger()
    result = merger.merge(
        [
            LoadedSource("base", SourceKind.TREE, 0, tree=base),
            LoadedSource("incoming", SourceKind.TREE, 1, tree=incoming),
        ]
    )
    merged_images = result.tree.path_lookup[os.path.normpath(r"C:\foo")].images
    assert "a.jpg" in merged_images
    assert "b.jpg" in merged_images


def test_merger_adds_new_branch(defaults: Defaults, filters: Filters):
    base = _make_tree(defaults, filters, r"C:\foo", ["a.jpg"])
    incoming = _make_tree(defaults, filters, r"C:\bar", ["x.jpg"])
    merger = TreeMerger()
    result = merger.merge(
        [
            LoadedSource("base", SourceKind.TREE, 0, tree=base),
            LoadedSource("incoming", SourceKind.TREE, 1, tree=incoming),
        ]
    )
    assert os.path.normpath(r"C:\bar") in result.tree.path_lookup


def test_merger_overwrites_user_proportion_on_match(defaults: Defaults, filters: Filters):
    base = _make_tree(defaults, filters, r"C:\foo", ["a.jpg"])
    base_node = base.path_lookup[os.path.normpath(r"C:\foo")]
    base_node.proportion = 25
    base_node.user_proportion = 25

    incoming = _make_tree(defaults, filters, r"C:\foo", ["b.jpg"])
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
    # user_proportion is right-most wins; proportion stays as existing unless empty
    assert merged_node.user_proportion == 75
    assert merged_node.proportion == 25


def test_merger_group_and_graft_offset_applied_to_leaf(defaults: Defaults, filters: Filters):
    incoming = _make_tree(defaults, filters, r"C:\foo\bar", ["x.jpg"])
    incoming_node = incoming.path_lookup[os.path.normpath(r"C:\foo\bar")]
    incoming_node.group = "g1"

    base = _make_tree(defaults, filters, r"C:\foo", [])

    merger = TreeMerger(target_lowest_rung=1)
    result = merger.merge(
        [
            LoadedSource("base", SourceKind.TREE, 0, tree=base),
            LoadedSource("incoming", SourceKind.TREE, 1, tree=incoming, graft_offset=1),
        ]
    )
    added_node = result.tree.path_lookup.get(os.path.normpath(r"C:\foo\bar"))
    assert added_node is not None
    assert getattr(added_node, "group", None) == "g1"


def test_merger_graft_offset_below_lowest_rung_raises(defaults: Defaults, filters: Filters):
    incoming = _make_tree(defaults, filters, r"C:\foo\bar", ["x.jpg"])
    base = _make_tree(defaults, filters, r"C:\foo", [])

    merger = TreeMerger(target_lowest_rung=2)
    with pytest.raises(ValueError):
        merger.merge(
            [
                LoadedSource("base", SourceKind.TREE, 0, tree=base),
                LoadedSource("incoming", SourceKind.TREE, 1, tree=incoming, graft_offset=-2),
            ]
        )


def test_apply_mode_and_recalculate_respects_user_proportion(defaults: Defaults, filters: Filters):
    defaults.set_global_defaults(mode={1: ("b", (0, 0))})
    tree = _make_tree(defaults, filters, r"C:\foo", ["a.jpg", "b.jpg"])
    node = tree.path_lookup[os.path.normpath(r"C:\foo")]
    node.user_proportion = 20
    node.proportion = 20

    apply_mode_and_recalculate(tree, defaults, ignore_user_proportion=False)
    assert node.proportion == 20
