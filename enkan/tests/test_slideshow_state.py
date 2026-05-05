from types import SimpleNamespace
import logging

from PIL import Image

from enkan.config import AppConfig, Config
from enkan.cache.CachedVideoData import CachedVideoData
from enkan.mySlideshow.MediaFileOps import ExifWriteResult
from enkan.mySlideshow.NavigationTypes import NavigationBasis, NavigationState, ScopeKind
from enkan.mySlideshow.mySlideshow import ImageSlideshow
from enkan.mySlideshow.ScopeStack import ScopeStack
from enkan.mySlideshow.VideoPlaybackController import VideoPlaybackController
from enkan.tree.selection_scope import SelectionScope


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
        resolve_node_for_image=lambda path: child,
        resolve_container_node_for_image=lambda path: child,
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


def test_initial_navigation_basis_uses_config_branch():
    config = Config(app_config=AppConfig(values={"navigation_basis": "branch"}))

    basis = ImageSlideshow._initial_navigation_basis(config)

    assert basis is NavigationBasis.BRANCH


def test_initial_navigation_basis_uses_config_folder():
    config = Config(app_config=AppConfig(values={"navigation_basis": "folder"}))

    basis = ImageSlideshow._initial_navigation_basis(config)

    assert basis is NavigationBasis.FOLDER


def test_initial_navigation_mode_matches_original_navigation_state():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    config = Config(app_config=AppConfig(values={"navigation_basis": "branch"}))
    basis = ImageSlideshow._initial_navigation_basis(config)
    slideshow.original_navigation_state = NavigationState(
        basis=basis,
        scope_kind=ScopeKind.ROOT,
    )
    slideshow.navigation_mode = slideshow.original_navigation_state.basis.value

    assert slideshow.original_navigation_state.basis is NavigationBasis.BRANCH
    assert slideshow.navigation_mode == "branch"


def test_select_mode_enables_crw_when_not_active():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.current_image_index = 4
    provider_calls: list[tuple[str, dict[str, object]]] = []
    slideshow.set_provider = lambda name, **kwargs: provider_calls.append((name, kwargs))
    slideshow.providers = SimpleNamespace(
        get_current_provider_name=lambda: "weighted",
        get_current_provider_settings=lambda: {},
    )

    slideshow.select_mode(SimpleNamespace(char="d"))

    assert provider_calls == [("controlled_random_weighted", {"gap_min": 3})]


def test_select_mode_toggles_crw_bucket_mode_when_active():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.current_image_index = 4
    provider_calls: list[tuple[str, dict[str, object]]] = []
    slideshow.set_provider = lambda name, **kwargs: provider_calls.append((name, kwargs))
    slideshow.providers = SimpleNamespace(
        get_current_provider_name=lambda: "controlled_random_weighted",
        get_current_provider_settings=lambda: {
            "gap_min": 7,
            "repeat_penalty": 0.2,
            "bucket_mode": "balance_bucket",
        },
    )

    slideshow.select_mode(SimpleNamespace(char="d"))

    assert provider_calls == [
        (
            "controlled_random_weighted",
            {
                "gap_min": 7,
                "repeat_penalty": 0.2,
                "bucket_mode": "folder_bucket",
            },
        )
    ]


def test_set_provider_seeds_status_from_current_media_without_history_record():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.image_paths = ["root\\folder\\one.jpg"]
    slideshow.current_image_path = "root\\folder\\one.jpg"
    slideshow.current_image_index = 0
    slideshow.defaults = SimpleNamespace(background=False)
    slideshow.selection_weights = SimpleNamespace(
        provider_kwargs=lambda: {"weights": [1.0]},
        weights=[1.0],
    )
    slideshow.selection_scope = None
    slideshow.original_tree = None
    slideshow.folder_memory = SimpleNamespace()
    slideshow.scope_seen_folders = set()
    slideshow.status_bar = SimpleNamespace()
    slideshow._resolve_memory_key_for_image = lambda path, meta=None: "root\\folder"
    slideshow._resolve_memory_key_for_scope = lambda path: path
    slideshow._scope_records_once_per_folder = lambda: False
    slideshow._sync_original_scope_memory = lambda: None

    provider_events = []
    context_calls = []
    manager = SimpleNamespace(
        history_snapshot=lambda: ("history",),
        restore_history=lambda snapshot: None,
    )
    slideshow.manager = manager
    slideshow.providers = SimpleNamespace(
        select_manager=lambda **kwargs: manager,
        configure_runtime_context=lambda context: context_calls.append(context),
        on_media_displayed=lambda event: provider_events.append(event),
    )

    slideshow.set_provider("controlled_random_weighted", gap_min=3)

    assert context_calls
    assert len(provider_events) == 1
    assert provider_events[0].image_path == "root\\folder\\one.jpg"
    assert provider_events[0].record_history is False
    assert provider_events[0].provider_pick_meta is None


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


def test_apply_scope_state_restores_navigation_modes_from_snapshot():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.original_tree = SimpleNamespace(
        find_node=lambda path, lookup: SimpleNamespace(name=path),
        node_lookup={},
    )
    slideshow.selection_weights = SimpleNamespace(copy=lambda: "copy-before")
    slideshow.folder_memory = SimpleNamespace(copy=lambda: "mem-before")
    slideshow.scope_seen_folders = {"before"}
    slideshow.navigation_mode = "folder"
    slideshow.parent_mode = False
    slideshow.subfolder_mode = False
    slideshow.navigation_node = None

    class _SelectionWeights:
        def copy(self):
            return "copy-after"

    class _FolderMemory:
        def copy(self):
            return "mem-after"

    scope_state = SimpleNamespace(
        selection_weights=_SelectionWeights(),
        folder_memory=_FolderMemory(),
        navigation_state=NavigationState(
            basis=NavigationBasis.BRANCH,
            scope_kind=ScopeKind.PARENT,
            branch_anchor="root\\branch",
        ),
        seen_folders={"seen"},
    )

    slideshow._apply_scope_state(scope_state)

    assert slideshow.navigation_mode == "branch"
    assert slideshow.parent_mode is True
    assert slideshow.subfolder_mode is False
    assert slideshow.navigation_node.name == "root\\branch"
    assert slideshow.scope_seen_folders == {"seen"}


def test_reset_parent_mode_restores_original_navigation_state():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.parentFolderStack = ScopeStack(5)
    slideshow.subFolderStack = ScopeStack(1)
    slideshow.parent_mode = True
    slideshow.subfolder_mode = True
    slideshow.navigation_mode = "folder"
    slideshow.navigation_node = None
    slideshow.original_navigation_state = NavigationState(
        basis=NavigationBasis.BRANCH,
        scope_kind=ScopeKind.ROOT,
        branch_anchor="root\\branch",
    )
    slideshow.original_tree = SimpleNamespace(
        find_node=lambda path, lookup: SimpleNamespace(name=path),
        node_lookup={},
    )
    slideshow.original_image_paths = ["a.jpg"]
    slideshow.original_selection_weights = SimpleNamespace(copy=lambda: "sel")
    slideshow.original_folder_memory = SimpleNamespace(copy=lambda: "mem")
    slideshow.original_scope_seen_folders = {"seen"}
    slideshow.current_image_index = 0
    provider_clears: list[str] = []
    slideshow.providers = SimpleNamespace(
        clear_provider_runtime_state=lambda: provider_clears.append("clear")
    )
    slideshow.update_slide_show = lambda image_paths, selection_weights: None
    slideshow.show_image = lambda image_path, record_history=False: None

    slideshow.reset_parent_mode()

    assert slideshow.parent_mode is False
    assert slideshow.subfolder_mode is False
    assert slideshow.navigation_mode == "branch"
    assert slideshow.navigation_node.name == "root\\branch"
    assert provider_clears == ["clear"]


def test_toggle_navigation_mode_preserves_selected_basis_when_resetting_scope():
    container_node = SimpleNamespace(name="root\\branch", parent=None)
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.navigation_mode = "folder"
    slideshow.current_image_path = "root\\branch\\image.jpg"
    slideshow.parent_mode = True
    slideshow.subfolder_mode = False
    slideshow.navigation_node = None
    slideshow.parentFolderStack = ScopeStack(5)
    slideshow.subFolderStack = ScopeStack(1)
    slideshow.original_image_paths = ["root\\branch\\image.jpg"]
    slideshow.original_selection_weights = SimpleNamespace(copy=lambda: "sel")
    slideshow.original_folder_memory = SimpleNamespace(copy=lambda: "mem")
    slideshow.original_scope_seen_folders = set()
    slideshow.original_navigation_state = NavigationState(
        basis=NavigationBasis.FOLDER,
        scope_kind=ScopeKind.ROOT,
    )
    slideshow.current_image_index = 0
    slideshow.original_tree = SimpleNamespace(
        resolve_node_for_image=lambda path: container_node if path == "root\\branch\\image.jpg" else None,
        resolve_container_node_for_image=lambda path: container_node if path == "root\\branch\\image.jpg" else None,
    )
    slideshow.update_slide_show = lambda image_paths, selection_weights: None
    slideshow.show_image = lambda image_path, record_history=False: None

    slideshow.toggle_navigation_mode()

    assert slideshow.navigation_mode == "branch"
    assert slideshow.navigation_node is None
    assert slideshow.parent_mode is False
    assert slideshow.subfolder_mode is False
    assert slideshow.original_navigation_state.basis is NavigationBasis.BRANCH
    assert slideshow.original_navigation_state.scope_kind is ScopeKind.ROOT


def test_find_container_node_for_image_ignores_virtual_image_lookup():
    container_node = SimpleNamespace(name="root\\retrobride")
    virtual_node = SimpleNamespace(name="root\\retrobride\\specific")
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.original_tree = SimpleNamespace(
        virtual_image_lookup={"root\\retrobride\\image.jpg": virtual_node},
        resolve_container_node_for_image=lambda path: container_node if path == "root\\retrobride\\image.jpg" else None,
    )

    node = slideshow.find_container_node_for_image("root\\retrobride\\image.jpg")

    assert node is container_node


def test_toggle_navigation_mode_allows_branch_mode_for_specific_image():
    container_node = SimpleNamespace(name="root\\retrobride")
    virtual_node = SimpleNamespace(name="root\\retrobride\\specific")
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.navigation_mode = "folder"
    slideshow.current_image_path = "root\\retrobride\\image.jpg"
    slideshow.parent_mode = False
    slideshow.subfolder_mode = False
    slideshow.navigation_node = None
    slideshow.parentFolderStack = ScopeStack(5)
    slideshow.subFolderStack = ScopeStack(1)
    slideshow.original_image_paths = ["root\\retrobride\\image.jpg"]
    slideshow.original_selection_weights = SimpleNamespace(copy=lambda: "sel")
    slideshow.original_folder_memory = SimpleNamespace(copy=lambda: "mem")
    slideshow.original_scope_seen_folders = set()
    slideshow.original_navigation_state = NavigationState(
        basis=NavigationBasis.FOLDER,
        scope_kind=ScopeKind.ROOT,
    )
    slideshow.current_image_index = 0
    slideshow.original_tree = SimpleNamespace(
        virtual_image_lookup={"root\\retrobride\\image.jpg": virtual_node},
        resolve_node_for_image=lambda path: virtual_node if path == "root\\retrobride\\image.jpg" else None,
        resolve_container_node_for_image=lambda path: container_node if path == "root\\retrobride\\image.jpg" else None,
    )
    slideshow.update_slide_show = lambda image_paths, selection_weights: None
    slideshow.show_image = lambda image_path, record_history=False: None

    slideshow.toggle_navigation_mode()

    assert slideshow.navigation_mode == "branch"
    assert slideshow.navigation_node is None
    assert slideshow.original_navigation_state.basis is NavigationBasis.BRANCH
    assert slideshow.original_navigation_state.scope_kind is ScopeKind.ROOT


def test_reset_parent_mode_preserves_branch_basis_after_navigation_toggle():
    container_node = SimpleNamespace(
        name="root\\branch",
        parent=SimpleNamespace(name="root"),
    )
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.navigation_mode = "folder"
    slideshow.current_image_path = "root\\branch\\image.jpg"
    slideshow.parent_mode = False
    slideshow.subfolder_mode = False
    slideshow.navigation_node = None
    slideshow.parentFolderStack = ScopeStack(5)
    slideshow.subFolderStack = ScopeStack(1)
    slideshow.original_image_paths = ["root\\branch\\image.jpg"]
    slideshow.original_selection_weights = SimpleNamespace(copy=lambda: "sel")
    slideshow.original_folder_memory = SimpleNamespace(copy=lambda: "mem")
    slideshow.original_scope_seen_folders = set()
    slideshow.original_navigation_state = NavigationState(
        basis=NavigationBasis.FOLDER,
        scope_kind=ScopeKind.ROOT,
    )
    slideshow.current_image_index = 0
    slideshow.original_tree = SimpleNamespace(
        find_node=lambda path, lookup: SimpleNamespace(name=path),
        node_lookup={},
        resolve_node_for_image=(
            lambda path: container_node if path == "root\\branch\\image.jpg" else None
        ),
        resolve_container_node_for_image=(
            lambda path: container_node if path == "root\\branch\\image.jpg" else None
        ),
    )
    slideshow.update_slide_show = lambda image_paths, selection_weights: None
    slideshow.show_image = lambda image_path, record_history=False: None

    slideshow.toggle_navigation_mode()
    slideshow.parent_mode = True
    slideshow.navigation_node = container_node.parent
    slideshow.reset_parent_mode()

    assert slideshow.navigation_mode == "branch"
    assert slideshow.parent_mode is False
    assert slideshow.subfolder_mode is False


def test_status_label_path_uses_exact_virtual_node_in_root_branch_mode():
    virtual_node = SimpleNamespace(name="root\\picture\\picked")
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.navigation_mode = "branch"
    slideshow.parent_mode = False
    slideshow.subfolder_mode = False
    slideshow.current_image_path = "root\\retrobride\\picked.jpg"
    slideshow.navigation_node = None
    slideshow.original_tree = SimpleNamespace(
        resolve_node_for_image=lambda path: virtual_node if path == "root\\retrobride\\picked.jpg" else None,
    )

    assert slideshow._status_label_path() == "root\\picture\\picked\\picked.jpg"


def test_status_label_path_uses_dynamic_container_node_for_regular_image_in_root_branch_mode():
    container_node = SimpleNamespace(name="root\\retrobride")
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.navigation_mode = "branch"
    slideshow.parent_mode = False
    slideshow.subfolder_mode = False
    slideshow.current_image_path = "root\\retrobride\\image.jpg"
    slideshow.navigation_node = None
    slideshow.original_tree = SimpleNamespace(
        resolve_node_for_image=lambda path: container_node if path == "root\\retrobride\\image.jpg" else None,
        resolve_container_node_for_image=lambda path: container_node if path == "root\\retrobride\\image.jpg" else None,
    )

    assert slideshow._status_label_path() == "root\\retrobride\\image.jpg"


def test_current_branch_context_node_uses_exact_tree_node_even_in_scoped_branch_mode():
    virtual_node = SimpleNamespace(name="root\\picture\\picked")
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.navigation_mode = "branch"
    slideshow.parent_mode = True
    slideshow.subfolder_mode = False
    slideshow.navigation_node = SimpleNamespace(name="root\\wedding")
    slideshow.current_image_path = "root\\retrobride\\image.jpg"
    slideshow.original_tree = SimpleNamespace(
        resolve_node_for_image=lambda path: virtual_node,
    )

    assert slideshow._current_branch_context_node() is virtual_node


def test_subfolder_mode_on_in_root_branch_mode_uses_current_tree_node(monkeypatch):
    current_node = SimpleNamespace(name="root\\picture\\picked")
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.navigation_mode = "branch"
    slideshow.parent_mode = False
    slideshow.subfolder_mode = False
    slideshow.navigation_node = None
    slideshow.current_image_path = "root\\retrobride\\image.jpg"
    slideshow.image_paths = ["root\\retrobride\\image.jpg"]
    slideshow.subFolderStack = ScopeStack(1)
    slideshow.selection_weights = SimpleNamespace(copy=lambda: "sel")
    slideshow.folder_memory = SimpleNamespace(copy=lambda: "mem")
    slideshow.scope_seen_folders = set()
    slideshow._capture_scope_state = lambda: "scope"
    slideshow._record_scope_entry = lambda path: recorded.append(path)
    slideshow._set_scope_kind = lambda kind: scope_kinds.append(kind)
    slideshow._new_scope_memory = lambda: "new-memory"
    slideshow.update_slide_show = lambda image_paths, selection_weights, record_initial_history=False, **kwargs: updates.append(
        (image_paths, selection_weights, record_initial_history)
    )
    slideshow.original_tree = SimpleNamespace(
        resolve_node_for_image=lambda path: current_node,
    )

    recorded: list[str] = []
    scope_kinds: list[ScopeKind] = []
    updates: list[tuple[object, object, bool]] = []

    monkeypatch.setattr(
        "enkan.mySlideshow.mySlideshow.extract_selection_scope_from_tree",
        lambda tree, start_node: SelectionScope.single_unit(
            node_key=current_node.name,
            image_paths=["root\\retrobride\\image.jpg"],
            weights=[1],
        ),
    )

    slideshow.subfolder_mode_on()

    assert recorded == ["root\\picture\\picked"]
    assert scope_kinds == [ScopeKind.SUBFOLDER]
    assert updates and updates[0][0] == ["root\\retrobride\\image.jpg"]


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
    slideshow.zoompan = SimpleNamespace(
        rotation_angle=90,
        update_exif_orientation=lambda orientation: setattr(
            slideshow.zoompan,
            "updated_orientation",
            orientation,
        ),
    )
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
    assert slideshow.zoompan.updated_orientation == 6
    assert shown == [("image.jpg", False)]


def test_rotate_image_ignores_video_without_restarting(monkeypatch):
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.current_image_path = "clip.mp4"
    slideshow.zoompan = SimpleNamespace(
        rotation_angle=0,
        rotate_display=lambda *_: (_ for _ in ()).throw(
            AssertionError("video rotation should not touch image display")
        ),
    )
    slideshow.show_image = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("video rotation should not restart playback")
    )
    monkeypatch.setattr("enkan.mySlideshow.mySlideshow.utils.is_videofile", lambda path: True)
    monkeypatch.setattr("enkan.mySlideshow.mySlideshow.utils.is_imagefile", lambda path: False)

    assert slideshow.rotate_image() == "break"
    assert slideshow.zoompan.rotation_angle == 0


def test_rotate_image_still_rotates_images(monkeypatch):
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.current_image_path = "image.jpg"
    rotations: list[int] = []
    slideshow.zoompan = SimpleNamespace(rotate_display=lambda delta: rotations.append(delta))
    monkeypatch.setattr("enkan.mySlideshow.mySlideshow.utils.is_videofile", lambda path: False)
    monkeypatch.setattr("enkan.mySlideshow.mySlideshow.utils.is_imagefile", lambda path: True)

    assert slideshow.rotate_image() == "break"

    assert rotations == [-90]


def test_show_image_allows_history_item_outside_current_scope():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.image_paths = ["scope\\one.jpg", "scope\\two.jpg"]
    slideshow.current_image_index = 1
    slideshow.current_image_path = "scope\\two.jpg"
    slideshow.current_exif_orientation = 1
    slideshow.rotation_angle = 0
    slideshow.video_muted = False
    slideshow.screen_width = 100
    slideshow.screen_height = 100
    slideshow._release_video_resources = lambda: None
    slideshow.providers = SimpleNamespace(
        get_current_provider_name=lambda: "weighted",
        get_current_provider_display_mode=lambda: "off",
    )
    slideshow.zoompan = SimpleNamespace(set_image=lambda image, **kwargs: None)
    slideshow.label = SimpleNamespace(pack=lambda: None, config=lambda **kwargs: None, image=None)
    slideshow.status_bar = SimpleNamespace(raise_widgets=lambda: None)
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


def test_show_image_notifies_provider_on_same_image_redisplay():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.image_paths = ["scope\\one.jpg"]
    slideshow.current_image_index = 0
    slideshow.current_image_path = "scope\\one.jpg"
    slideshow.current_exif_orientation = 1
    slideshow.rotation_angle = 0
    slideshow.video_muted = False
    slideshow.screen_width = 100
    slideshow.screen_height = 100
    slideshow._release_video_resources = lambda: None
    provider_events = []
    slideshow.providers = SimpleNamespace(
        get_current_provider_name=lambda: "controlled_random_weighted",
        get_current_provider_display_mode=lambda: "useful",
        on_media_displayed=lambda event: provider_events.append(event),
    )
    slideshow.selection_weights = SimpleNamespace(weights=[1.0])
    slideshow.folder_memory = SimpleNamespace()
    slideshow.zoompan = SimpleNamespace(set_image=lambda image, **kwargs: None)
    slideshow.label = SimpleNamespace(pack=lambda: None, config=lambda **kwargs: None, image=None)
    slideshow.status_bar = SimpleNamespace(raise_widgets=lambda: None)
    slideshow.root = SimpleNamespace(after=lambda *args, **kwargs: None)
    slideshow.manager = SimpleNamespace(
        get_next=lambda image_path=None, record_history=True: (
            "scope\\one.jpg",
            Image.new("RGB", (1, 1)),
        )
    )

    slideshow.show_image("scope\\one.jpg", record_history=False)

    assert len(provider_events) == 1
    assert provider_events[0].image_path == "scope\\one.jpg"
    assert provider_events[0].previous_image_path == "scope\\one.jpg"
    assert provider_events[0].record_history is False


def test_show_image_notifies_provider_after_display_and_status_raise():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.image_paths = ["scope\\one.jpg"]
    slideshow.current_image_index = 0
    slideshow.current_image_path = None
    slideshow.current_exif_orientation = 1
    slideshow.rotation_angle = 0
    slideshow.video_muted = False
    slideshow.screen_width = 100
    slideshow.screen_height = 100
    slideshow._release_video_resources = lambda: None
    slideshow.providers = SimpleNamespace(
        get_current_provider_name=lambda: "weighted",
        get_current_provider_display_mode=lambda: "off",
        on_media_displayed=lambda event: order.append(
            (
                "provider",
                event.image_path,
                event.record_history,
                event.provider_pick_meta,
            )
        ),
    )
    slideshow.zoompan = SimpleNamespace(set_image=lambda image, **kwargs: order.append("display"))
    slideshow.label = SimpleNamespace(pack=lambda: None, config=lambda **kwargs: None, image=None)
    slideshow.status_bar = SimpleNamespace(
        raise_widgets=lambda: order.append("status-raise")
    )
    slideshow.root = SimpleNamespace(after=lambda *args, **kwargs: None)
    slideshow.manager = SimpleNamespace(
        current_media_metadata={"index": 0, "memory_key": "root\\scope"},
        get_next=lambda image_path=None, record_history=True: (
            "scope\\one.jpg",
            Image.new("RGB", (1, 1)),
        ),
    )

    order: list[str] = []

    slideshow.show_image()

    assert order == [
        "display",
        "status-raise",
        ("provider", "scope\\one.jpg", True, {"index": 0, "memory_key": "root\\scope"}),
    ]


def test_show_image_debounces_rapid_video_start_requests(monkeypatch):
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.image_paths = ["videos\\one.mp4", "videos\\two.mp4"]
    slideshow.current_image_index = 0
    slideshow.current_image_path = None
    slideshow.current_exif_orientation = 1
    slideshow.rotation_angle = 0
    slideshow.video_muted = False
    slideshow.screen_width = 100
    slideshow.screen_height = 100
    slideshow.selection_weights = SimpleNamespace(weights=[1.0, 1.0])
    slideshow.folder_memory = SimpleNamespace()
    slideshow.original_tree = None
    slideshow.providers = SimpleNamespace(
        get_current_provider_name=lambda: "weighted",
        get_current_provider_display_mode=lambda: "off",
    )
    slideshow.zoompan = SimpleNamespace(clear_image=lambda: None)
    slideshow.label = SimpleNamespace(pack=lambda: None, config=lambda **kwargs: None, image=None)
    slideshow.status_bar = SimpleNamespace(raise_widgets=lambda: None)
    slideshow.runtime_status_text = ""

    scheduled = {}
    cancelled: list[str] = []
    after_counter = {"value": 0}

    def after(delay, callback):
        after_counter["value"] += 1
        ident = f"after-{after_counter['value']}"
        scheduled[ident] = callback
        return ident

    def after_cancel(ident):
        cancelled.append(ident)
        scheduled.pop(ident, None)

    slideshow.root = SimpleNamespace(after=after, after_cancel=after_cancel)
    slideshow.video_controller = VideoPlaybackController(
        root=slideshow.root,
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )

    payloads = {
        "videos\\one.mp4": CachedVideoData(path="videos\\one.mp4", data=b"one"),
        "videos\\two.mp4": CachedVideoData(path="videos\\two.mp4", data=b"two"),
    }
    requested_paths: list[str] = []
    slideshow.manager = SimpleNamespace(
        current_media_metadata=None,
        get_next=lambda image_path=None, record_history=True: (
            image_path,
            payloads[image_path],
        ),
    )

    monkeypatch.setattr("enkan.mySlideshow.mySlideshow.utils.is_videofile", lambda path: True)

    def fake_start_video_playback(
        request_id,
        image_path,
        media_payload,
        muted,
        on_video_started=None,
        on_status_changed=None,
    ):
        requested_paths.append(image_path)
        on_video_started()

    slideshow.video_controller._start_video_playback = fake_start_video_playback

    slideshow.show_image("videos\\one.mp4")
    slideshow.show_image("videos\\two.mp4")

    assert cancelled == ["after-1"]
    assert list(scheduled) == ["after-2"]

    scheduled["after-2"]()

    assert requested_paths == ["videos\\two.mp4"]


def test_stop_offloads_cleanup_to_background_thread(monkeypatch):
    controller = VideoPlaybackController(
        root=SimpleNamespace(after_cancel=lambda _: None),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )

    events: list[str] = []

    class _Player:
        def stop(self):
            events.append("stop")

        def release(self):
            events.append("player-release")

    class _Media:
        def get_mrl(self):
            return "file:///broken.mp4"

        def release(self):
            events.append("media-release")

    started_targets: list[tuple[object, tuple]] = []

    class _FakeThread:
        def __init__(self, target, args=(), daemon=None):
            self.target = target
            self.args = args

        def start(self):
            started_targets.append((self.target, self.args))

    monkeypatch.setattr(
        "enkan.mySlideshow.VideoPlaybackController.threading.Thread",
        _FakeThread,
    )

    controller._video_player = _Player()
    controller._current_media = _Media()
    controller._current_video_payload = object()

    controller.stop(async_cleanup=True)

    assert controller._video_player is None
    assert controller._current_media is None
    assert controller._current_video_payload is None
    assert events == []
    assert len(started_targets) == 1

    cleanup_target, cleanup_args = started_targets[0]
    cleanup_target(*cleanup_args)

    assert events == ["stop", "player-release", "media-release"]


def test_stop_hides_video_frame_and_cancels_pending_replay():
    cancelled: list[str] = []
    forgotten: list[str] = []
    controller = VideoPlaybackController(
        root=SimpleNamespace(after_cancel=lambda ident: cancelled.append(ident)),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )
    controller._pending_replay_id = "replay"
    controller._video_frame = SimpleNamespace(place_forget=lambda: forgotten.append("hide"))

    controller.stop(async_cleanup=True, hide=True)

    assert cancelled == ["replay"]
    assert forgotten == ["hide"]


def test_start_video_playback_defers_while_cleanup_active():
    controller = VideoPlaybackController(
        root=SimpleNamespace(after=lambda *_: None),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )
    controller._video_start_request_id = 2
    controller._pending_video_start_id = None
    controller._video_cleanup_done.clear()

    scheduled: list[tuple[int, object]] = []
    controller.root = SimpleNamespace(
        after=lambda delay, callback: scheduled.append((delay, callback)) or "after-1"
    )

    controller._start_video_playback(2, "videos\\one.mp4", None, False, None)

    assert controller._pending_video_start_id == "after-1"
    assert len(scheduled) == 1
    assert scheduled[0][0] == 30


def test_start_video_playback_releases_media_when_player_setup_fails(monkeypatch):
    controller = VideoPlaybackController(
        root=SimpleNamespace(after_cancel=lambda _: None),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )
    controller._video_start_request_id = 1
    forgotten: list[str] = []
    controller._video_frame = SimpleNamespace(
        place=lambda **kwargs: None,
        update_idletasks=lambda: None,
        lift=lambda: None,
        winfo_id=lambda: 123,
        place_forget=lambda: forgotten.append("hide"),
    )

    events: list[str] = []

    class _Media:
        def get_mrl(self):
            return "file:///broken.mp4"

        def release(self):
            events.append("media-release")

    class _Player:
        def set_media(self, media):
            raise RuntimeError("set_media failed")

        def stop(self):
            events.append("player-stop")

        def release(self):
            events.append("player-release")

    class _VlcInstance:
        def media_new(self, path):
            return _Media()

        def media_player_new(self):
            return _Player()

    class _ImmediateThread:
        def __init__(self, target, args=(), daemon=None):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(
        "enkan.mySlideshow.VideoPlaybackController.threading.Thread",
        _ImmediateThread,
    )
    controller._vlc_instance = _VlcInstance()
    statuses: list[str] = []

    controller._start_video_playback(
        1,
        "videos\\broken.mp4",
        None,
        False,
        on_status_changed=statuses.append,
    )

    assert statuses == ["Video playback failed"]
    assert forgotten == ["hide"]
    assert events == ["player-stop", "player-release", "media-release"]
    assert controller._video_player is None
    assert controller._current_media is None


def test_controller_end_event_schedules_replay_on_tk_thread():
    controller = VideoPlaybackController(
        root=SimpleNamespace(
            after=lambda delay, callback: scheduled.append((delay, callback)) or "replay"
        ),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )
    controller._video_start_request_id = 3

    scheduled: list[tuple[int, object]] = []

    controller._on_video_end_reached(None, 3)

    assert controller._pending_replay_id == "replay"
    assert len(scheduled) == 1
    assert scheduled[0][0] == 0


def test_controller_replay_ended_video_restarts_player():
    controller = VideoPlaybackController(
        root=SimpleNamespace(),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )
    controller._video_start_request_id = 3
    controller._pending_replay_id = "replay"

    events: list[str] = []

    class _Player:
        def stop(self):
            events.append("stop")

        def play(self):
            events.append("play")
            return 0

    controller._video_player = _Player()

    controller._replay_ended_video(3)

    assert events == ["stop", "play"]
    assert controller._pending_replay_id is None


def test_controller_replay_failure_is_recoverable(monkeypatch):
    controller = VideoPlaybackController(
        root=SimpleNamespace(after_cancel=lambda _: None),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )
    controller._video_start_request_id = 3
    forgotten: list[str] = []
    controller._video_frame = SimpleNamespace(place_forget=lambda: forgotten.append("hide"))
    statuses: list[str] = []
    controller._on_status_changed = statuses.append
    events: list[str] = []

    class _Player:
        def stop(self):
            events.append("player-stop")

        def play(self):
            raise RuntimeError("play failed")

        def release(self):
            events.append("player-release")

    class _ImmediateThread:
        def __init__(self, target, args=(), daemon=None):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(
        "enkan.mySlideshow.VideoPlaybackController.threading.Thread",
        _ImmediateThread,
    )
    controller._video_player = _Player()

    controller._replay_ended_video(3)

    assert statuses == ["Video playback failed"]
    assert forgotten == ["hide"]
    assert events == ["player-stop", "player-stop", "player-release"]
    assert controller._video_player is None


def test_controller_ignores_stale_end_event():
    controller = VideoPlaybackController(
        root=SimpleNamespace(after=lambda *_: (_ for _ in ()).throw(AssertionError("stale event should not schedule"))),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )
    controller._video_start_request_id = 3

    controller._on_video_end_reached(None, 2)

    assert controller._pending_replay_id is None


def test_controller_ignores_duplicate_end_event_while_replay_pending():
    controller = VideoPlaybackController(
        root=SimpleNamespace(
            after=lambda *_: (_ for _ in ()).throw(
                AssertionError("duplicate event should not schedule")
            )
        ),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )
    controller._video_start_request_id = 3
    controller._pending_replay_id = "replay"

    controller._on_video_end_reached(None, 3)

    assert controller._pending_replay_id == "replay"


def test_controller_replay_does_not_restart_while_paused():
    controller = VideoPlaybackController(
        root=SimpleNamespace(),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )
    controller._video_start_request_id = 3
    controller._is_paused = True
    controller._video_player = SimpleNamespace(
        stop=lambda: (_ for _ in ()).throw(AssertionError("should not replay")),
        play=lambda: (_ for _ in ()).throw(AssertionError("should not replay")),
    )

    controller._replay_ended_video(3)

    assert controller._video_player is not None


def test_controller_toggle_pause_updates_player_pause_state():
    class _Sink:
        def __init__(self):
            self.contributions = []
            self.cleared = []

        def set_contribution(self, contribution):
            self.contributions.append(contribution)

        def set_contributions(self, contributions):
            self.contributions.extend(contributions)

        def clear_contribution(self, key):
            self.cleared.append(key)

    sink = _Sink()
    controller = VideoPlaybackController(
        root=SimpleNamespace(),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
        status_sink=sink,
    )
    pause_values: list[int] = []
    controller._video_player = SimpleNamespace(
        set_pause=lambda value: pause_values.append(value),
        get_time=lambda: 250,
        get_length=lambda: 1000,
    )

    assert controller.toggle_pause() is True
    assert controller.toggle_pause() is False

    assert pause_values == [1, 0]
    assert [contribution.key for contribution in sink.contributions] == [
        "video-timer",
        "video-timer",
    ]
    assert sink.contributions[0].content.paused is True
    assert sink.contributions[1].content.paused is False


def test_controller_toggle_pause_failure_sets_status():
    controller = VideoPlaybackController(
        root=SimpleNamespace(),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )
    statuses: list[str] = []
    controller._on_status_changed = statuses.append
    controller._video_player = SimpleNamespace(
        set_pause=lambda value: (_ for _ in ()).throw(RuntimeError("pause failed"))
    )

    assert controller.toggle_pause() is False
    assert controller._is_paused is False
    assert statuses == ["Video control failed"]


def test_controller_seek_to_ratio_clamps_and_uses_duration():
    controller = VideoPlaybackController(
        root=SimpleNamespace(),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )
    set_times: list[int] = []
    controller._video_player = SimpleNamespace(
        get_time=lambda: 100,
        get_length=lambda: 1000,
        set_time=lambda value: set_times.append(value),
    )

    assert controller.seek_to_ratio(1.5) is True

    assert set_times == [1000]


def test_controller_seek_relative_clamps_to_current_duration():
    class _Sink:
        def __init__(self):
            self.contributions = []

        def set_contribution(self, contribution):
            self.contributions.append(contribution)

        def set_contributions(self, contributions):
            self.contributions.extend(contributions)

        def clear_contribution(self, key):
            pass

    sink = _Sink()
    controller = VideoPlaybackController(
        root=SimpleNamespace(),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
        status_sink=sink,
    )
    set_times: list[int] = []
    controller._video_player = SimpleNamespace(
        get_time=lambda: 900,
        get_length=lambda: 1000,
        set_time=lambda value: set_times.append(value),
    )

    assert controller.seek_relative_ms(5000) is True
    assert controller.seek_relative_ms(-950) is True

    assert set_times == [1000, 0]
    assert [contribution.key for contribution in sink.contributions] == [
        "video-timer",
        "video-timer",
    ]


def test_controller_seek_ignores_unknown_duration():
    controller = VideoPlaybackController(
        root=SimpleNamespace(),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )
    controller._video_player = SimpleNamespace(
        get_time=lambda: 100,
        get_length=lambda: -1,
        set_time=lambda value: (_ for _ in ()).throw(AssertionError("should not seek")),
    )

    assert controller.seek_to_ratio(0.5) is False


def test_controller_seek_failure_sets_status():
    class _Sink:
        def __init__(self):
            self.contributions = []
            self.cleared = []

        def set_contribution(self, contribution):
            self.contributions.append(contribution)

        def set_contributions(self, contributions):
            self.contributions.extend(contributions)

        def clear_contribution(self, key):
            self.cleared.append(key)

    sink = _Sink()
    controller = VideoPlaybackController(
        root=SimpleNamespace(),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
        status_sink=sink,
    )
    statuses: list[str] = []
    controller._on_status_changed = statuses.append
    controller._video_player = SimpleNamespace(
        get_time=lambda: 100,
        get_length=lambda: 1000,
        set_time=lambda value: (_ for _ in ()).throw(RuntimeError("seek failed")),
    )

    assert controller.seek_relative_ms(5000) is False
    assert statuses == ["Video control failed"]
    assert any(
        contribution.key == "video-runtime-status"
        and contribution.content == "VIDEO: Video control failed"
        for contribution in sink.contributions
    )


def test_video_pause_hotkey_delegates_status_update_to_controller():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    class _Controller:
        def __init__(self):
            self.active = True

        def toggle_pause(self):
            return True

        def playback_snapshot(self):
            return SimpleNamespace(active=self.active)

    slideshow.video_controller = _Controller()

    assert slideshow.toggle_video_pause() == "break"


def test_video_seek_hotkey_delegates_status_update_to_controller():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    deltas: list[int] = []
    slideshow.video_controller = SimpleNamespace(
        seek_relative_ms=lambda delta: deltas.append(delta) or True
    )

    assert slideshow.seek_video_by_ms(-5000) == "break"

    assert deltas == [-5000]


def test_controller_playback_snapshot_handles_active_and_inactive_states():
    controller = VideoPlaybackController(
        root=SimpleNamespace(),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )

    inactive = controller.playback_snapshot()
    assert inactive.active is False
    assert inactive.seekable is False

    controller._is_paused = True
    controller._video_player = SimpleNamespace(
        get_time=lambda: 250,
        get_length=lambda: 1000,
    )

    active = controller.playback_snapshot()
    assert active.active is True
    assert active.paused is True
    assert active.current_time_ms == 250
    assert active.duration_ms == 1000
    assert active.seekable is True
    assert active.progress_ratio == 0.25


def test_shutdown_stops_synchronously_releases_vlc_instance_and_destroys_frame():
    controller = VideoPlaybackController(
        root=SimpleNamespace(after_cancel=lambda _: None),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
    )
    events: list[str] = []

    class _Player:
        def stop(self):
            events.append("stop")

        def release(self):
            events.append("player-release")

    class _Media:
        def release(self):
            events.append("media-release")

    class _VlcInstance:
        def release(self):
            events.append("vlc-release")

    class _Frame:
        def destroy(self):
            events.append("frame-destroy")

    controller._video_player = _Player()
    controller._current_media = _Media()
    controller._vlc_instance = _VlcInstance()
    controller._video_frame = _Frame()

    controller.shutdown()

    assert events == [
        "stop",
        "player-release",
        "media-release",
        "vlc-release",
        "frame-destroy",
    ]
    assert controller._vlc_instance is None
    assert controller._video_frame is None


def test_shutdown_detaches_status_sink_before_synchronous_cleanup():
    class _Sink:
        def set_contribution(self, contribution):
            raise AssertionError("shutdown should not publish status")

        def set_contributions(self, contributions):
            raise AssertionError("shutdown should not publish status")

        def clear_contribution(self, key):
            raise AssertionError("shutdown should not clear status")

    events: list[str] = []
    controller = VideoPlaybackController(
        root=SimpleNamespace(after_cancel=lambda ident: events.append(f"cancel:{ident}")),
        screen_width=100,
        screen_height=100,
        logger=logging.getLogger("test"),
        debounce_ms=150,
        status_sink=_Sink(),
    )
    controller._status_refresh_id = "refresh"
    controller._video_player = SimpleNamespace(
        stop=lambda: events.append("stop"),
        release=lambda: events.append("player-release"),
    )
    controller._current_media = SimpleNamespace(release=lambda: events.append("media-release"))

    controller.shutdown()

    assert events == ["cancel:refresh", "stop", "player-release", "media-release"]
    assert controller.status_sink is None


def test_toggle_mute_updates_preference_and_active_player():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.video_muted = False
    applied: list[bool] = []
    slideshow.video_controller = SimpleNamespace(
        set_muted=lambda muted: applied.append(muted)
    )

    slideshow.toggle_mute()
    slideshow.toggle_mute()

    assert applied == [True, False]
    assert slideshow.video_muted is False


def test_show_image_does_not_create_slideshow_vlc_state_for_images():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.image_paths = ["scope\\one.jpg"]
    slideshow.current_image_index = 0
    slideshow.current_image_path = None
    slideshow.current_exif_orientation = 1
    slideshow.rotation_angle = 0
    slideshow.video_muted = False
    slideshow.screen_width = 100
    slideshow.screen_height = 100
    slideshow._release_video_resources = lambda: None
    slideshow.providers = SimpleNamespace(
        get_current_provider_name=lambda: "weighted",
        get_current_provider_display_mode=lambda: "off",
    )
    slideshow.zoompan = SimpleNamespace(set_image=lambda image, **kwargs: None)
    slideshow.label = SimpleNamespace(pack=lambda: None, config=lambda **kwargs: None, image=None)
    slideshow.status_bar = SimpleNamespace(raise_widgets=lambda: None)
    slideshow.manager = SimpleNamespace(
        current_media_metadata=None,
        get_next=lambda image_path=None, record_history=True: (
            "scope\\one.jpg",
            Image.new("RGB", (1, 1)),
        ),
    )

    slideshow.show_image()

    assert not hasattr(slideshow, "current_vlc_media")
    assert not hasattr(slideshow, "current_video_payload")


def test_runtime_status_publishes_to_status_sink():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.runtime_status_text = ""
    events: list[tuple[str, str]] = []
    slideshow.status_bar = SimpleNamespace(
        set_contribution=lambda contribution: events.append(
            ("set", contribution.content)
        ),
        clear_contribution=lambda key: events.append(("clear", key)),
    )

    slideshow._set_runtime_status("No displayable media")
    slideshow._set_runtime_status("")

    assert events == [
        ("set", "No displayable media"),
        ("clear", "runtime-status"),
    ]


def test_auto_advance_status_publishes_to_status_sink():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    events: list[tuple[str, str]] = []
    slideshow.status_bar = SimpleNamespace(
        set_contribution=lambda contribution: events.append(
            ("set", contribution.content)
        ),
        clear_contribution=lambda key: events.append(("clear", key)),
    )

    slideshow.auto_advance_running = True
    slideshow.auto_advance_interval = 5000
    slideshow._publish_auto_advance_status()
    slideshow.auto_advance_running = False
    slideshow._publish_auto_advance_status()

    assert events == [
        ("set", "AUTO (5000ms)  "),
        ("clear", "auto-advance"),
    ]


def test_count_status_publishes_to_status_sink():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.current_image_path = "two.jpg"
    slideshow.image_paths = ["one.jpg", "two.jpg"]
    slideshow.current_image_index = 0
    events: list[tuple[str, str]] = []
    slideshow.status_bar = SimpleNamespace(
        set_contribution=lambda contribution: events.append(
            ("set", contribution.content)
        )
    )

    slideshow._publish_count_status()

    assert events == [("set", "(2/2)")]


def test_scope_status_publishes_to_status_sink():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    events: list[tuple[str, str]] = []
    slideshow.status_bar = SimpleNamespace(
        set_contribution=lambda contribution: events.append(
            ("set", contribution.content)
        ),
        clear_contribution=lambda key: events.append(("clear", key)),
    )

    slideshow.subfolder_mode = True
    slideshow.parent_mode = True
    slideshow._publish_scope_status()
    slideshow.subfolder_mode = False
    slideshow.parent_mode = False
    slideshow._publish_scope_status()

    assert events == [
        ("set", "SUB PAR"),
        ("clear", "scope"),
    ]


def test_toggle_filename_display_sets_status_visibility_without_monolithic_refresh():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.show_filename = False
    slideshow.current_image_path = "two.jpg"
    slideshow.image_paths = ["one.jpg", "two.jpg"]
    slideshow.current_image_index = 1
    slideshow.navigation_mode = "folder"
    slideshow.parent_mode = False
    slideshow.subfolder_mode = False
    slideshow.navigation_node = None
    visibility: list[bool] = []
    contributions: list[str] = []
    slideshow.status_bar = SimpleNamespace(
        set_contribution=lambda contribution: contributions.append(contribution.key),
        clear_contribution=lambda key: None,
        set_base_contributions=lambda contributions, *, visible: visibility.append(visible),
    )

    slideshow.toggle_filename_display()
    slideshow.toggle_filename_display()

    assert visibility == [True, False]
    assert contributions == ["filepath", "count"]


def test_cache_dots_hotkey_toggles_status_contribution_visibility():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    toggled: list[str] = []
    slideshow.status_bar = SimpleNamespace(
        toggle_contribution_visibility=lambda key: toggled.append(key)
    )

    assert slideshow.toggle_cache_dots() == "break"
    assert toggled == ["cache-dots"]
