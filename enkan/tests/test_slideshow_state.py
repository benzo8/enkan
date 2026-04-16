from types import SimpleNamespace

from PIL import Image

from enkan.mySlideshow.MediaFileOps import ExifWriteResult
from enkan.mySlideshow.NavigationTypes import NavigationBasis, NavigationState, ScopeKind
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
    slideshow._last_burst_memory_token = "token"

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
    assert slideshow._last_burst_memory_token is None


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
    slideshow._last_burst_memory_token = "token"
    slideshow.update_slide_show = lambda image_paths, selection_weights: None
    slideshow.show_image = lambda image_path, record_history=False: None

    slideshow.reset_parent_mode()

    assert slideshow.parent_mode is False
    assert slideshow.subfolder_mode is False
    assert slideshow.navigation_mode == "branch"
    assert slideshow.navigation_node.name == "root\\branch"
    assert slideshow._last_burst_memory_token is None


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
    slideshow._last_burst_memory_token = None
    slideshow.original_tree = SimpleNamespace(
        resolve_container_node_for_image=lambda path: container_node if path == "root\\branch\\image.jpg" else None,
    )
    slideshow.update_slide_show = lambda image_paths, selection_weights: None
    slideshow.show_image = lambda image_path, record_history=False: None
    slideshow.update_filename_display = lambda: None

    slideshow.toggle_navigation_mode()

    assert slideshow.navigation_mode == "branch"
    assert slideshow.navigation_node is None
    assert slideshow.parent_mode is False
    assert slideshow.subfolder_mode is False


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


def test_toggle_navigation_mode_uses_container_node_for_specific_image():
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
    slideshow._last_burst_memory_token = None
    slideshow.original_tree = SimpleNamespace(
        virtual_image_lookup={"root\\retrobride\\image.jpg": virtual_node},
        resolve_container_node_for_image=lambda path: container_node if path == "root\\retrobride\\image.jpg" else None,
    )
    slideshow.update_slide_show = lambda image_paths, selection_weights: None
    slideshow.show_image = lambda image_path, record_history=False: None
    slideshow.update_filename_display = lambda: None

    slideshow.toggle_navigation_mode()

    assert slideshow.navigation_mode == "branch"
    assert slideshow.navigation_node is None


def test_status_label_path_uses_dynamic_container_node_in_root_branch_mode():
    container_node = SimpleNamespace(name="root\\retrobride")
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.navigation_mode = "branch"
    slideshow.parent_mode = False
    slideshow.subfolder_mode = False
    slideshow.current_image_path = "root\\retrobride\\image.jpg"
    slideshow.navigation_node = None
    slideshow.original_tree = SimpleNamespace(
        resolve_container_node_for_image=lambda path: container_node if path == "root\\retrobride\\image.jpg" else None,
    )

    assert slideshow._status_label_path() == "root\\retrobride\\image.jpg"


def test_current_branch_context_node_uses_current_image_container_even_in_scoped_branch_mode():
    container_node = SimpleNamespace(name="root\\retrobride")
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.navigation_mode = "branch"
    slideshow.parent_mode = True
    slideshow.subfolder_mode = False
    slideshow.navigation_node = SimpleNamespace(name="root\\wedding")
    slideshow.current_image_path = "root\\retrobride\\image.jpg"
    slideshow.original_tree = SimpleNamespace(
        resolve_container_node_for_image=lambda path: container_node,
    )

    assert slideshow._current_branch_context_node() is container_node


def test_subfolder_mode_on_in_root_branch_mode_uses_container_node(monkeypatch):
    container_node = SimpleNamespace(name="root\\retrobride")
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
    slideshow.update_slide_show = lambda image_paths, selection_weights, record_initial_history=False: updates.append(
        (image_paths, selection_weights, record_initial_history)
    )
    slideshow.original_tree = SimpleNamespace(
        resolve_container_node_for_image=lambda path: container_node,
    )

    recorded: list[str] = []
    scope_kinds: list[ScopeKind] = []
    updates: list[tuple[object, object, bool]] = []

    monkeypatch.setattr(
        "enkan.mySlideshow.mySlideshow.extract_image_paths_and_weights_from_tree",
        lambda tree, start_node: (["root\\retrobride\\image.jpg"], [1])
    )

    slideshow.subfolder_mode_on()

    assert recorded == ["root\\retrobride"]
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
    slideshow.current_provider_status_payload = None
    slideshow.video_muted = False
    slideshow.screen_width = 100
    slideshow.screen_height = 100
    slideshow._release_video_resources = lambda: None
    slideshow.providers = SimpleNamespace(
        get_current_provider_name=lambda: "weighted",
        get_current_provider_display_mode=lambda: "off",
    )
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


def test_show_image_preserves_provider_payload_on_same_image_redisplay():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.image_paths = ["scope\\one.jpg"]
    slideshow.current_image_index = 0
    slideshow.current_image_path = "scope\\one.jpg"
    slideshow.current_provider_status_payload = {"kept": True}
    slideshow.current_exif_orientation = 1
    slideshow.rotation_angle = 0
    slideshow.video_muted = False
    slideshow.screen_width = 100
    slideshow.screen_height = 100
    slideshow._release_video_resources = lambda: None
    slideshow.providers = SimpleNamespace(
        get_current_provider_name=lambda: "controlled_random_weighted",
        get_current_provider_display_mode=lambda: "useful",
        get_current_provider_status_payload=lambda **kwargs: {"recomputed": True},
    )
    slideshow.selection_weights = SimpleNamespace(weights=[1.0])
    slideshow.folder_memory = SimpleNamespace()
    slideshow._record_memory_for_view = lambda image_path, record_history: None
    slideshow.zoompan = SimpleNamespace(set_image=lambda image: None)
    slideshow.label = SimpleNamespace(pack=lambda: None, config=lambda **kwargs: None, image=None)
    slideshow.filename_label = SimpleNamespace(tkraise=lambda: None)
    slideshow.mode_label = SimpleNamespace(tkraise=lambda: None)
    slideshow.update_filename_display = lambda: None
    slideshow.root = SimpleNamespace(after=lambda *args, **kwargs: None)
    slideshow.manager = SimpleNamespace(
        get_next=lambda image_path=None, record_history=True: (
            "scope\\one.jpg",
            Image.new("RGB", (1, 1)),
        )
    )

    slideshow.show_image("scope\\one.jpg", record_history=False)

    assert slideshow.current_provider_status_payload == {"kept": True}
