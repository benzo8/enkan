from types import SimpleNamespace

from PIL import Image

from enkan.mySlideshow.MediaFileOps import ExifWriteResult
from enkan.mySlideshow.NavigationTypes import NavigationBasis, ScopeKind
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


def test_navigation_state_reports_basis_and_scope_kind():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.navigation_mode = "branch"
    slideshow.parent_mode = True
    slideshow.subfolder_mode = False
    slideshow.navigation_node = SimpleNamespace(name="root\\branch")

    state = slideshow._navigation_state()

    assert state.basis is NavigationBasis.BRANCH
    assert state.scope_kind is ScopeKind.PARENT
    assert state.branch_anchor == "root\\branch"


def test_navigation_state_prefers_subfolder_scope_over_parent_flag():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.navigation_mode = "folder"
    slideshow.parent_mode = True
    slideshow.subfolder_mode = True
    slideshow.navigation_node = None

    state = slideshow._navigation_state()

    assert state.basis is NavigationBasis.FOLDER
    assert state.scope_kind is ScopeKind.SUBFOLDER
    assert state.branch_anchor is None


def test_delete_image_uses_media_file_op_and_updates_state(monkeypatch):
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.current_image_path = "b.jpg"
    slideshow.current_image_index = 1
    slideshow.image_paths = ["a.jpg", "b.jpg", "c.jpg"]

    removed_indexes = []

    class _SelectionWeights:
        def remove_at(self, index):
            removed_indexes.append(index)

    removed_from_history = []

    class _HistoryManager:
        def remove(self, path):
            removed_from_history.append(path)

    slideshow.selection_weights = _SelectionWeights()
    slideshow.manager = SimpleNamespace(history_manager=_HistoryManager())
    slideshow._confirm_action = lambda title, message: True
    slideshow._release_video_resources = lambda: None
    slideshow._sync_original_scope_state = lambda: None
    slideshow.exit_slideshow = lambda: (_ for _ in ()).throw(AssertionError("should not exit"))

    deleted_paths = []
    monkeypatch.setattr(
        "enkan.mySlideshow.mySlideshow.delete_media_file",
        lambda path: deleted_paths.append(path),
    )

    updates = []
    slideshow.update_slide_show = lambda image_paths, selection_weights, preferred_index=None, **kwargs: updates.append(
        (list(image_paths), selection_weights, preferred_index)
    )

    slideshow.delete_image()

    assert deleted_paths == ["b.jpg"]
    assert slideshow.image_paths == ["a.jpg", "c.jpg"]
    assert removed_indexes == [1]
    assert removed_from_history == ["b.jpg"]
    assert slideshow.current_image_index == 1
    assert slideshow.current_image_path == "c.jpg"
    assert updates and updates[0][0] == ["a.jpg", "c.jpg"]
    assert updates[0][2] == 1


def test_delete_image_ignores_missing_history_entry(monkeypatch):
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.current_image_path = "b.jpg"
    slideshow.current_image_index = 1
    slideshow.image_paths = ["a.jpg", "b.jpg", "c.jpg"]
    slideshow.selection_weights = SimpleNamespace(remove_at=lambda index: None)
    slideshow._confirm_action = lambda title, message: True
    slideshow._release_video_resources = lambda: None
    slideshow._sync_original_scope_state = lambda: None
    slideshow.exit_slideshow = lambda: (_ for _ in ()).throw(AssertionError("should not exit"))

    class _HistoryManager:
        def remove(self, path):
            raise ValueError(f"{path} is not in deque")

    slideshow.manager = SimpleNamespace(history_manager=_HistoryManager())
    monkeypatch.setattr(
        "enkan.mySlideshow.mySlideshow.delete_media_file",
        lambda path: None,
    )

    updates = []
    slideshow.update_slide_show = lambda image_paths, selection_weights, preferred_index=None, **kwargs: updates.append(
        (list(image_paths), preferred_index)
    )

    slideshow.delete_image()

    assert slideshow.current_image_path == "c.jpg"
    assert slideshow.current_image_index == 1
    assert updates == [(["a.jpg", "c.jpg"], 1)]


def test_persist_rotation_to_exif_uses_file_op_result(monkeypatch):
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.current_image_path = "image.jpg"
    slideshow.rotation_angle = 90
    slideshow.current_exif_orientation = 1
    slideshow._confirm_action = lambda title, message: True

    warnings = []
    slideshow._show_warning = lambda title, message: warnings.append((title, message))

    invalidated = []
    slideshow.manager = SimpleNamespace(invalidate=lambda path: invalidated.append(path))

    shown = []
    slideshow.show_image = lambda path, record_history=False: shown.append((path, record_history))

    monkeypatch.setattr("enkan.mySlideshow.mySlideshow.utils.is_imagefile", lambda path: True)
    monkeypatch.setattr("enkan.mySlideshow.mySlideshow.utils.is_videofile", lambda path: False)
    monkeypatch.setattr(
        "enkan.mySlideshow.mySlideshow.write_exif_orientation",
        lambda path, rotation_angle: ExifWriteResult(new_orientation=6),
    )

    slideshow.persist_rotation_to_exif()

    assert warnings == []
    assert invalidated == ["image.jpg"]
    assert slideshow.rotation_angle == 0
    assert slideshow.current_exif_orientation == 6
    assert shown == [("image.jpg", False)]


def test_show_image_allows_history_item_outside_current_scope():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.image_paths = ["scope\\one.jpg", "scope\\two.jpg"]
    slideshow.current_image_index = 1
    slideshow.current_image_path = "scope\\two.jpg"
    slideshow.current_exif_orientation = 1
    slideshow.rotation_angle = 0
    slideshow.current_crw_metrics = None
    slideshow.video_muted = False
    slideshow.screen_width = 100
    slideshow.screen_height = 100
    slideshow._release_video_resources = lambda: None
    slideshow.providers = SimpleNamespace(get_current_provider_name=lambda: "weighted")
    slideshow._current_crw_display_mode = lambda: "off"
    slideshow._record_memory_for_view = lambda image_path, record_history: None
    slideshow.zoompan = SimpleNamespace(set_image=lambda image: None)
    slideshow.label = SimpleNamespace(pack=lambda: None, config=lambda **kwargs: None, image=None)
    slideshow.filename_label = SimpleNamespace(tkraise=lambda: None)
    slideshow.mode_label = SimpleNamespace(tkraise=lambda: None)
    slideshow.update_filename_display = lambda: None
    slideshow.root = SimpleNamespace(after=lambda *args, **kwargs: None)
    slideshow.manager = SimpleNamespace(
        get_next=lambda image_path=None, record_history=True: (
            "other\\seen-before.jpg",
            Image.new("RGB", (1, 1)),
        )
    )

    slideshow.show_image("other\\seen-before.jpg", record_history=False)

    assert slideshow.current_image_path == "other\\seen-before.jpg"
    assert slideshow.current_image_index == 1
