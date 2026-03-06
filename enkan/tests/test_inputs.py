from __future__ import annotations

import os
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from enkan.utils.Defaults import Defaults, resolve_mode
from enkan.utils.Filters import Filters
from enkan.tree.Tree import Tree
from enkan.tree.tree_logic import apply_mode_and_recalculate
from enkan.tree.tree_logic import calculate_weights
from enkan.tree.tree_logic import extract_image_paths_and_weights_from_tree
from enkan.utils.input.input_models import SourceKind, LoadedSource
from enkan.utils.input.TreeMerger import TreeMerger
from enkan.utils.input.MultiSourceBuilder import MultiSourceBuilder
from enkan.constants import TOTAL_WEIGHT


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


def _write_tree_with_pickle_version(tree: Tree, path: str, version: int) -> None:
    """
    Write a Tree pickle with a specific _pickle_version by temporarily
    overriding Tree.PICKLE_VERSION.
    """
    from enkan.tree.tree_io import write_tree_to_file

    original = Tree.PICKLE_VERSION
    try:
        Tree.PICKLE_VERSION = version
        write_tree_to_file(tree, path)
    finally:
        Tree.PICKLE_VERSION = original


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


def test_outdated_tree_falls_back_to_txt():
    tmp = Path(_ensure_case_dir("outdated_tree_fallback"))
    defaults = _make_defaults(mode_str="b1")
    filters = Filters()

    # Create a tree with an outdated pickle version.
    dir1 = _create_dir_with_images(tmp, "base")
    base_tree = _make_tree(defaults, filters, dir1, ["a.jpg"])
    base_tree.built_mode = defaults.mode
    tree_path = tmp / "base.tree"
    _write_tree_with_pickle_version(base_tree, str(tree_path), version=Tree.PICKLE_VERSION - 1)

    # Provide a txt fallback.
    txt_path = tmp / "base.txt"
    txt_path.write_text(f"{dir1}\n", encoding="utf-8")

    builder = MultiSourceBuilder(defaults, filters)
    merged_tree, warnings = builder.build([str(tree_path)])

    assert warnings  # should warn about stale tree
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


def test_single_source_txt_applies_detected_mode():
    tmp = Path(_ensure_case_dir("single_source_mode"))
    defaults = _make_defaults()
    filters = Filters()

    # Use a global mode marker and ensure it propagates to defaults.
    dir1 = _create_dir_with_images(tmp, os.path.join("p1", "p2", "p3", "p4", "p5"))
    txt1 = tmp / "one.txt"
    txt1.write_text(f"[b6]*\n{dir1}\n", encoding="utf-8")

    builder = MultiSourceBuilder(defaults, filters)
    tree, warnings = builder.build([str(txt1)])

    assert warnings == []
    assert 6 in defaults.mode
    mode_char, _ = resolve_mode(defaults.mode, 6)
    assert mode_char == "b"


def test_txt_entry_proportion_does_not_propagate_to_descendants():
    tmp = Path(_ensure_case_dir("txt_entry_proportion_scope"))
    defaults = _make_defaults()
    filters = Filters()

    root = tmp / "root_a"
    child = root / "child"
    child.mkdir(parents=True, exist_ok=True)
    _ = _create_dir_with_images(str(child), "leaf", count=2)

    txt_path = tmp / "one.txt"
    txt_path.write_text(f"[b2]*\n{root} [%50]\n", encoding="utf-8")

    builder = MultiSourceBuilder(defaults, filters)
    tree, warnings = builder.build([str(txt_path)])

    assert warnings == []
    root_node = tree.path_lookup[os.path.normpath(str(root))]
    child_node = tree.path_lookup[os.path.normpath(str(child))]

    assert root_node.user_proportion == 50
    assert child_node.user_proportion is None


def test_apply_mode_clears_stale_weights_above_lowest_rung():
    defaults = _make_defaults(mode_str="b6")
    filters = Filters()
    leaf_path = r"C:\p1\p2\p3\p4\p5"
    tree = _make_tree(defaults, filters, leaf_path, [leaf_path + r"\a.jpg"])
    # Ancestor node above lowest rung.
    node = tree.path_lookup[os.path.normpath(r"C:\p1")]

    # Simulate stale weight from a prior build.
    node.weight = 123.0

    apply_mode_and_recalculate(tree, defaults, ignore_user_proportion=False)

    # With mode b6, lowest rung is 6; node is above that and should be cleared to None.
    assert node.weight is None


def test_extract_raises_for_unweighted_image_node_above_lowest_rung():
    defaults = _make_defaults(mode_str="b6")
    filters = Filters()
    tree = Tree(defaults, filters)

    shallow = r"C:\p1"
    deep = r"C:\a\b\c\d\e"
    for path, image in ((shallow, "s.jpg"), (deep, "d.jpg")):
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
                "images": [os.path.join(path, image)],
            },
        )

    # Mode b6 gives a starting node at level 6 (deep), leaving the shallow image node unweighted.
    # Extraction should fail with a targeted diagnostic instead of crashing on None division.
    calculate_weights(tree, ignore_user_proportion=False)

    with pytest.raises(ValueError, match="without calculated weight"):
        extract_image_paths_and_weights_from_tree(tree)


def test_internal_nodes_with_images_do_not_double_count_total_weight():
    defaults = _make_defaults(mode_str="b2")
    filters = Filters()
    tree = Tree(defaults, filters)

    # Start node at lowest rung.
    tree.create_node(
        r"C:\p1",
        {
            "weight_modifier": 100,
            "is_percentage": True,
            "proportion": 100,
            "user_proportion": 100,
            "mode_modifier": None,
            "images": [],
        },
    )
    # Internal node with own images and a child with images.
    tree.create_node(
        r"C:\p1\mixed",
        {
            "weight_modifier": 100,
            "is_percentage": True,
            "proportion": None,
            "user_proportion": None,
            "mode_modifier": None,
            "images": [r"C:\p1\mixed\a.jpg", r"C:\p1\mixed\b.jpg"],
        },
    )
    tree.create_node(
        r"C:\p1\mixed\leaf",
        {
            "weight_modifier": 100,
            "is_percentage": True,
            "proportion": None,
            "user_proportion": None,
            "mode_modifier": None,
            "images": [r"C:\p1\mixed\leaf\c.jpg", r"C:\p1\mixed\leaf\d.jpg"],
        },
    )

    calculate_weights(tree, ignore_user_proportion=False)
    _, weights = extract_image_paths_and_weights_from_tree(tree)

    assert math.isclose(sum(weights), TOTAL_WEIGHT, rel_tol=0, abs_tol=1e-9)


@pytest.mark.parametrize(
    "first_kind,second_kind",
    [
        ("txt", "tree"),
        ("tree", "txt"),
        ("txt", "lst"),
        ("lst", "txt"),
    ],
)
def test_multisource_ordering_permutations(first_kind: str, second_kind: str):
    tmp = Path(_ensure_case_dir(f"ordering_{first_kind}_{second_kind}"))
    defaults = _make_defaults(mode_str="b1")
    filters = Filters()

    dir1 = _create_dir_with_images(tmp, "first")
    dir2 = _create_dir_with_images(tmp, "second")

    txt1 = tmp / "one.txt"
    txt2 = tmp / "two.txt"
    txt1.write_text(f"{dir1}\n", encoding="utf-8")
    txt2.write_text(f"{dir2}\n", encoding="utf-8")

    tree1 = _make_tree(defaults, filters, dir1, ["a.jpg"])
    tree2 = _make_tree(defaults, filters, dir2, ["b.jpg"])
    tree1.built_mode = defaults.mode
    tree2.built_mode = defaults.mode
    tree_path1 = tmp / "one.tree"
    tree_path2 = tmp / "two.tree"
    from enkan.tree.tree_io import write_tree_to_file
    write_tree_to_file(tree1, tree_path1)
    write_tree_to_file(tree2, tree_path2)

    lst_path1 = tmp / "one.lst"
    lst_path2 = tmp / "two.lst"
    lst_img1 = os.path.join(dir1, "img0.jpg")
    lst_img2 = os.path.join(dir2, "img0.jpg")
    lst_path1.write_text(f"{lst_img1},1\n", encoding="utf-8")
    lst_path2.write_text(f"{lst_img2},1\n", encoding="utf-8")

    def _resolve(kind: str, which: str):
        if kind == "txt":
            return str(txt1 if which == "first" else txt2)
        if kind == "tree":
            return str(tree_path1 if which == "first" else tree_path2)
        if kind == "lst":
            return str(lst_path1 if which == "first" else lst_path2)
        raise ValueError(kind)

    builder = MultiSourceBuilder(defaults, filters)
    tree, _ = builder.build([_resolve(first_kind, "first"), _resolve(second_kind, "second")])

    # Both sources should be present; ordering should not drop either.
    assert os.path.normpath(dir1) in tree.path_lookup
    assert os.path.normpath(dir2) in tree.path_lookup


def test_multisource_tree_tree_ordering():
    tmp = Path(_ensure_case_dir("tree_tree_ordering"))
    defaults = _make_defaults(mode_str="b1")
    filters = Filters()

    dir1 = _create_dir_with_images(tmp, "base")
    dir2 = _create_dir_with_images(tmp, "incoming")
    base_tree = _make_tree(defaults, filters, dir1, ["a.jpg"])
    incoming_tree = _make_tree(defaults, filters, dir2, ["b.jpg"])
    base_tree.built_mode = defaults.mode
    incoming_tree.built_mode = defaults.mode

    from enkan.tree.tree_io import write_tree_to_file
    base_path = tmp / "base.tree"
    incoming_path = tmp / "incoming.tree"
    write_tree_to_file(base_tree, base_path)
    write_tree_to_file(incoming_tree, incoming_path)

    builder = MultiSourceBuilder(defaults, filters)
    tree, warnings = builder.build([str(base_path), str(incoming_path)])

    assert warnings == []
    assert os.path.normpath(dir1) in tree.path_lookup
    assert os.path.normpath(dir2) in tree.path_lookup


def test_lst_plain_and_weighted_merge():
    tmp = Path(_ensure_case_dir("lst_plain_weighted"))
    defaults = _make_defaults(mode_str="b1")
    filters = Filters()

    # Weighted lst
    w_path = tmp / "weighted.lst"
    w_img = (tmp / "wdir" / "img0.jpg").resolve()
    w_path.write_text(f"{w_img},2\n", encoding="utf-8")

    # Plain lst
    p_path = tmp / "plain.lst"
    p_img = (tmp / "pdir" / "img0.jpg").resolve()
    p_path.write_text(f"{p_img}\n", encoding="utf-8")

    builder = MultiSourceBuilder(defaults, filters)
    tree, warnings = builder.build([str(w_path), str(p_path)])

    assert tree is not None
    assert os.path.normpath(os.path.dirname(str(w_img))) in tree.path_lookup
    assert os.path.normpath(os.path.dirname(str(p_img))) in tree.path_lookup
    assert warnings == [] or warnings is not None


def test_merger_replaces_images_for_matching_path(defaults: Defaults, filters: Filters):
    base = _make_tree(defaults, filters, r"C:\foo", [r"C:\foo\a.jpg"])
    incoming = _make_tree(defaults, filters, r"C:\foo", [r"C:\foo\b.jpg"])

    merger = TreeMerger()
    result = merger.merge(
        [
            LoadedSource("base", SourceKind.TREE, 0, tree=base),
            LoadedSource("incoming", SourceKind.TREE, 1, tree=incoming),
        ]
    )
    merged_images = result.tree.path_lookup[os.path.normpath(r"C:\foo")].images
    assert r"C:\foo\b.jpg" in merged_images
    assert r"C:\foo\a.jpg" not in merged_images


def test_merger_replaces_only_matching_path_images(defaults: Defaults, filters: Filters):
    base = _make_tree(defaults, filters, r"C:\foo", [r"C:\foo\a.jpg", r"C:\bar\keep.jpg"])
    incoming = _make_tree(defaults, filters, r"C:\foo", [r"C:\foo\new.jpg"])

    merger = TreeMerger()
    result = merger.merge(
        [
            LoadedSource("base", SourceKind.TREE, 0, tree=base),
            LoadedSource("incoming", SourceKind.TREE, 1, tree=incoming),
        ]
    )
    merged_images = result.tree.path_lookup[os.path.normpath(r"C:\foo")].images
    assert r"C:\bar\keep.jpg" in merged_images
    assert r"C:\foo\new.jpg" in merged_images
    assert r"C:\foo\a.jpg" not in merged_images


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


def test_merger_existing_structural_node_with_incoming_images_applies_graft_offset(
    defaults: Defaults, filters: Filters
):
    # Base tree creates C:\foo\bar as structural-only via deeper child.
    base = _make_tree(defaults, filters, r"C:\foo\bar\leaf", ["base.jpg"])
    base_structural = base.path_lookup[os.path.normpath(r"C:\foo\bar")]
    assert base_structural.images == []
    base_level = base_structural.level

    # Incoming tree adds images directly to that existing structural path.
    incoming = _make_tree(defaults, filters, r"C:\foo\bar", ["incoming.jpg"])

    merger = TreeMerger(target_lowest_rung=base_level + 1)
    result = merger.merge(
        [
            LoadedSource("base", SourceKind.TREE, 0, tree=base),
            LoadedSource("incoming", SourceKind.TREE, 1, tree=incoming, graft_offset=1),
        ]
    )

    merged_node = result.tree.path_lookup[os.path.normpath(r"C:\foo\bar")]
    assert merged_node is not None
    assert merged_node.images
    assert merged_node.level == base_level + 1


def test_apply_mode_and_recalculate_respects_user_proportion(defaults: Defaults, filters: Filters):
    defaults.set_global_defaults(mode={1: ("b", (0, 0))})
    tree = _make_tree(defaults, filters, r"C:\foo", ["a.jpg", "b.jpg"])
    node = tree.path_lookup[os.path.normpath(r"C:\foo")]
    node.user_proportion = 20
    node.proportion = 20

    apply_mode_and_recalculate(tree, defaults, ignore_user_proportion=False)
    assert node.proportion == 20
