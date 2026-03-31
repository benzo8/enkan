from types import SimpleNamespace

from enkan.mySlideshow.mySlideshow import ImageSlideshow
from enkan.mySlideshow.ScopeStack import ScopeStack


def test_safe_current_image_index_uses_current_path_when_present():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.current_image_path = "b.jpg"
    slideshow.current_image_index = 0

    assert slideshow.safe_current_image_index(["a.jpg", "b.jpg", "c.jpg"]) == 1


def test_safe_current_image_index_prefers_surviving_neighbor_after_deletion():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.current_image_path = "b.jpg"
    slideshow.current_image_index = 1

    assert slideshow.safe_current_image_index(["a.jpg", "c.jpg"], preferred_index=1) == 1


def test_safe_current_image_index_handles_empty_image_list():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.current_image_path = "gone.jpg"
    slideshow.current_image_index = 4

    assert slideshow.safe_current_image_index([]) == 0


def test_navigate_up_in_branch_mode_does_not_require_parent_scope_stack():
    grandparent = SimpleNamespace(name="root")
    parent = SimpleNamespace(name="root\\parent", parent=grandparent)
    child = SimpleNamespace(name="root\\parent\\child", parent=parent)

    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.parentFolderStack = ScopeStack(5)
    slideshow.parent_mode = True
    slideshow.navigation_mode = "branch"
    slideshow.current_image_path = "root\\parent\\child\\image.jpg"
    slideshow.navigation_node = grandparent
    slideshow.original_tree = SimpleNamespace(
        find_node=lambda path, lookup: child,
        path_lookup={},
    )
    slideshow.folder_memory = SimpleNamespace()
    slideshow.scope_seen_folders = {"seen"}
    slideshow._record_scope_entry = lambda folder: None
    slideshow._new_scope_memory = lambda: "new-memory"

    calls: list[tuple[object, object, bool]] = []
    slideshow.traverse_directory = lambda path, node, record_initial_history=False: calls.append(
        (path, node, record_initial_history)
    )

    slideshow.navigate_up()

    assert slideshow.navigation_node is parent
    assert slideshow.folder_memory == "new-memory"
    assert slideshow.scope_seen_folders == set()
    assert calls == [(None, parent, True)]
