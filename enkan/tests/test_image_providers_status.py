from enkan.plugables.ImageProviders import ImageProviders


class _FakeNode:
    def __init__(self, name, level, parent=None):
        self.name = name
        self._level = level
        self.parent = parent

    @property
    def level(self):
        return self._level

    def ancestor_at_level(self, target_level):
        if target_level < 1 or target_level > self.level:
            return None
        current = self
        while current is not None and current.level > target_level:
            current = current.parent
        return current


class _FakeTree:
    def __init__(self, image_to_node, folder_to_node, mode_map):
        self.virtual_image_lookup = dict(image_to_node)
        self.path_lookup = dict(folder_to_node)
        self.defaults = type("_Defaults", (), {"mode": mode_map})()
        self.built_mode = mode_map

    def resolve_node_for_image(self, image_path):
        node = self.virtual_image_lookup.get(image_path)
        if node is not None:
            return node
        import os

        return self.path_lookup.get(os.path.dirname(image_path))

    def find_node(self, name, lookup_dict=None):
        lookup = self.path_lookup if lookup_dict is None else lookup_dict
        return lookup.get(name)


def test_image_providers_returns_current_provider_label():
    providers = ImageProviders()
    providers.current_provider_name = "controlled_random_weighted"

    assert providers.get_current_provider_label() == "CRW"


def test_image_providers_returns_empty_status_for_non_crw():
    providers = ImageProviders()
    providers.current_provider_name = "weighted"

    assert providers.get_current_provider_status(
        display_mode="debug",
        status_payload={"age": 5},
    ) == ""


def test_image_providers_formats_crw_provider_status():
    providers = ImageProviders()
    providers.current_provider_name = "controlled_random_weighted"

    text = providers.get_current_provider_status(
        display_mode="friendly",
        status_payload={
            "age": 5,
            "seen_before": False,
            "streak_len": 0,
            "folder_factor": 1.0,
            "boost": 1.0,
            "streak_factor": 1.0,
            "combined": 1.0,
            "bias_pct": 0.0,
            "bucket_mode": "balance_bucket",
        },
    )

    assert text == "BB NEW"


def test_image_providers_builds_crw_status_payload():
    providers = ImageProviders()
    providers.current_provider_name = "controlled_random_weighted"
    root = _FakeNode("root", 1)
    branch_a = _FakeNode("root\\a", 2, root)
    branch_b = _FakeNode("root\\b", 2, root)
    folder_a = _FakeNode("root\\a\\folder", 3, branch_a)
    folder_b = _FakeNode("root\\b\\folder", 3, branch_b)
    tree = _FakeTree(
        {
            "root\\a\\one.jpg": folder_a,
            "root\\b\\two.jpg": folder_b,
        },
        {
            "root\\a": branch_a,
            "root\\b": branch_b,
        },
        {2: ("b", (0, 0))},
    )

    class _FolderMemory:
        def has_seen(self, folder):
            return True

        def distance_for(self, folder):
            return 7

        def streak_for(self, folder):
            return 2

    payload = providers.get_current_provider_status_payload(
        image_paths=["root\\a\\one.jpg", "root\\b\\two.jpg"],
        weights=[2.0, 1.0],
        current_image_path="root\\a\\one.jpg",
        folder_memory=_FolderMemory(),
        tree=tree,
        settings={
            "gap_min": 3,
            "gap_max": 10,
            "alpha": 0.01,
            "repeat_penalty": 0.1,
            "bucket_mode": "folder_bucket",
        },
    )

    assert payload is not None
    assert payload["folder"] == "root\\a"
    assert payload["seen_before"] is True
    assert payload["streak_len"] == 2


def test_image_providers_returns_controlled_random_settings():
    providers = ImageProviders()

    settings = providers.get_controlled_random_settings(
        image_paths=["root\\a\\one.jpg", "root\\b\\two.jpg"],
        weights=[2.0, 1.0],
        gap_min=3,
        repeat_penalty=0.2,
        bucket_mode="folder_bucket",
    )

    assert settings["gap_min"] == 3
    assert settings["repeat_penalty"] == 0.2
    assert settings["gap_max"] >= 4
    assert settings["bucket_mode"] == "folder_bucket"


def test_image_providers_status_payload_uses_balanced_branch_bucket():
    providers = ImageProviders()
    providers.current_provider_name = "controlled_random_weighted"

    class _FolderMemory:
        step = 1
        last_seen_by_folder = {"root\\branch_a\\folder_1": 1}
        current_streak_folder = "root\\branch_a\\folder_1"
        current_streak_length = 1
        recent_folders = ["root\\branch_a\\folder_1"]

    root = _FakeNode("root", 1)
    branch_a = _FakeNode("root\\branch_a", 2, root)
    branch_b = _FakeNode("root\\branch_b", 2, root)
    folder_1 = _FakeNode("root\\branch_a\\folder_1", 3, branch_a)
    folder_2 = _FakeNode("root\\branch_a\\folder_2", 3, branch_a)
    folder_3 = _FakeNode("root\\branch_b\\folder_3", 3, branch_b)
    tree = _FakeTree(
        {
            "root\\branch_a\\folder_1\\one.jpg": folder_1,
            "root\\branch_a\\folder_2\\two.jpg": folder_2,
            "root\\branch_b\\folder_3\\three.jpg": folder_3,
        },
        {
            "root\\branch_a\\folder_1": folder_1,
            "root\\branch_a\\folder_2": folder_2,
            "root\\branch_b\\folder_3": folder_3,
        },
        {2: ("b", (0, 0))},
    )

    payload = providers.get_current_provider_status_payload(
        image_paths=[
            "root\\branch_a\\folder_1\\one.jpg",
            "root\\branch_a\\folder_2\\two.jpg",
            "root\\branch_b\\folder_3\\three.jpg",
        ],
        weights=[1.0, 1.0, 1.0],
        current_image_path="root\\branch_a\\folder_2\\two.jpg",
        folder_memory=_FolderMemory(),
        tree=tree,
        settings={
            "gap_min": 3,
            "gap_max": 10,
            "alpha": 0.01,
            "repeat_penalty": 0.1,
            "bucket_mode": "balance_bucket",
        },
    )

    assert payload is not None
    assert payload["bucket"] == "root\\branch_a"
    assert payload["bucket_mode"] == "balance_bucket"
    assert payload["seen_before"] is True


def test_image_providers_recomputes_crw_settings_on_same_provider_rebuild(monkeypatch):
    providers = ImageProviders()
    providers.register_provider(
        "controlled_random_weighted",
        lambda image_paths, **kwargs: iter(()),
    )

    monkeypatch.setattr(
        "enkan.plugables.ImageProviders.ImageCacheManager",
        lambda image_provider, current_image_index, background_preload=True, **kwargs: object(),
    )

    providers.select_manager(
        ["root\\branch_a\\folder_1\\one.jpg", "root\\branch_b\\folder_2\\two.jpg"],
        provider_name="controlled_random_weighted",
        weights=[1.0, 1.0],
        gap_min=5,
        repeat_penalty=0.2,
        tree=_FakeTree({}, {}, {2: ("b", (0, 0))}),
    )
    initial_settings = providers.get_current_provider_settings()

    providers.select_manager(
        [f"root\\branch_{i}\\folder\\file.jpg" for i in range(20)],
        provider_name="controlled_random_weighted",
        weights=[1.0] * 20,
        tree=_FakeTree({}, {}, {2: ("b", (0, 0))}),
    )
    rebuilt_settings = providers.get_current_provider_settings()

    assert rebuilt_settings["gap_min"] == 5
    assert rebuilt_settings["repeat_penalty"] == 0.2
    assert rebuilt_settings["gap_max"] > initial_settings["gap_max"]


def test_image_providers_cycles_display_mode_for_current_provider():
    providers = ImageProviders()
    providers.current_provider_name = "controlled_random_weighted"

    assert providers.get_current_provider_display_mode() == "off"
    assert providers.cycle_current_provider_display_mode() == "friendly"
    assert providers.cycle_current_provider_display_mode() == "useful"


def test_image_providers_preserves_display_mode_when_rebuilding_same_provider(monkeypatch):
    providers = ImageProviders()
    providers.register_provider("test_provider", lambda image_paths, **kwargs: iter(()))
    providers.current_provider_name = "test_provider"
    providers.provider_display_modes["test_provider"] = ("off", "detail", "debug")
    providers.current_provider_display_mode_index = 2

    monkeypatch.setattr(
        "enkan.plugables.ImageProviders.ImageCacheManager",
        lambda image_provider, current_image_index, background_preload=True, **kwargs: object(),
    )

    providers.select_manager([], provider_name="test_provider")

    assert providers.get_current_provider_display_mode() == "debug"
