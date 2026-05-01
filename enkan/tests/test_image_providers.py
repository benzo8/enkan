import os
import random

from enkan.plugables.FolderSelectionMemory import FolderSelectionMemory
from enkan.plugables.ImageProviders import ImageProviders
from enkan.tree.selection_scope import SelectionScope, SelectionUnit
from enkan.tree.diagnostics import _resolve_test_provider


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
        return self.path_lookup.get(os.path.dirname(image_path))

    def find_node(self, name, lookup_dict=None):
        lookup = self.path_lookup if lookup_dict is None else lookup_dict
        return lookup.get(name)


def _selection_scope_from_units(*units):
    image_paths: list[str] = []
    weights: list[float] = []
    selection_units: list[SelectionUnit] = []

    for node_key, node_level, ancestor_keys, unit_images, unit_weights in units:
        start_index = len(image_paths)
        image_paths.extend(unit_images)
        weights.extend(unit_weights)
        selection_units.append(
            SelectionUnit(
                node_key=node_key,
                node_level=node_level,
                ancestor_keys=ancestor_keys,
                image_paths=list(unit_images),
                weights=list(unit_weights),
                cum_weights=[sum(unit_weights[:i + 1]) for i in range(len(unit_weights))],
                base_total=sum(unit_weights),
                start_index=start_index,
            )
        )

    return SelectionScope.from_parts(image_paths, weights, selection_units)


def test_controlled_random_weighted_registered():
    providers = ImageProviders()

    assert "controlled_random_weighted" in providers.providers
    assert (
        _resolve_test_provider(providers.providers, "image_provider_controlled_random_weighted")
        == "controlled_random_weighted"
    )


def test_controlled_random_weighted_penalises_recent_folders():
    providers = ImageProviders()
    image_paths = [
        os.path.join("set_a", "a.jpg"),
        os.path.join("set_b", "b.jpg"),
        os.path.join("set_c", "c.jpg"),
    ]
    weights = [1.0, 1.0, 1.0]
    cum_weights = [1.0, 2.0, 3.0]
    folder_memory = FolderSelectionMemory()

    random.seed(1)
    provider = providers.image_provider_controlled_random_weighted(
        image_paths,
        weights=weights,
        cum_weights=cum_weights,
        folder_memory=folder_memory,
        gap_min=3,
        gap_max=10,
        alpha=0.01,
        repeat_penalty=0.0,
    )

    picks = []
    folders = []
    for _ in range(4):
        picked = next(provider)
        picks.append(picked)
        folder = os.path.dirname(picked)
        folders.append(folder)
        folder_memory.record_folder(folder)

    assert len(set(folders[:3])) == 3
    assert folders[3] in set(folders[:3])


def test_controlled_random_weighted_allows_single_folder_repeats():
    providers = ImageProviders()
    image_paths = [
        os.path.join("only", "a.jpg"),
        os.path.join("only", "b.jpg"),
    ]
    weights = [1.0, 3.0]
    cum_weights = [1.0, 4.0]
    folder_memory = FolderSelectionMemory()

    random.seed(2)
    provider = providers.image_provider_controlled_random_weighted(
        image_paths,
        weights=weights,
        cum_weights=cum_weights,
        folder_memory=folder_memory,
        gap_min=5,
        gap_max=10,
        alpha=0.01,
        repeat_penalty=0.0,
    )

    picks = []
    for _ in range(8):
        picked = next(provider)
        picks.append(picked)
        folder_memory.record_folder(os.path.dirname(picked))

    assert all(os.path.dirname(path) == "only" for path in picks)
    assert len(picks) == 8


def test_folder_selection_memory_updates_distance():
    memory = FolderSelectionMemory()

    assert memory.distance_for("folder_a") == 1
    assert memory.has_seen("folder_a") is False
    assert memory.streak_for("folder_a") == 0
    memory.record_folder("folder_a")
    assert memory.step == 1
    assert memory.has_seen("folder_a") is True
    assert memory.distance_for("folder_a") == 1
    assert memory.streak_for("folder_a") == 1
    memory.record_folder("folder_a")
    assert memory.streak_for("folder_a") == 2
    memory.record_folder("folder_b")
    assert memory.streak_for("folder_a") == 0
    assert memory.streak_for("folder_b") == 1


def test_burst_provider_exposes_memory_token(tmp_path):
    providers = ImageProviders()
    folder_a = tmp_path / "folder_a"
    folder_b = tmp_path / "folder_b"
    folder_a.mkdir()
    folder_b.mkdir()
    image_paths = []
    for folder, names in ((folder_a, ("a1.jpg", "a2.jpg")), (folder_b, ("b1.jpg", "b2.jpg"))):
        for name in names:
            path = folder / name
            path.write_text("x", encoding="utf-8")
            image_paths.append(str(path))
    cum_weights = [1.0, 2.0, 3.0, 4.0]

    random.seed(3)
    provider = providers.image_provider_folder_burst(
        image_paths,
        cum_weights=cum_weights,
        burst_size=2,
    )

    first = next(provider)
    first_token = provider.current_burst_token

    assert first_token is not None
    assert provider.current_burst_folder == os.path.dirname(first)
    provider.reset_burst()
    assert provider.current_burst_token is None
    assert provider.current_burst_folder is None


def test_controlled_random_weighted_does_not_mutate_memory_directly():
    providers = ImageProviders()
    folder_memory = FolderSelectionMemory()

    provider = providers.image_provider_controlled_random_weighted(
        [os.path.join("folder_a", "a.jpg"), os.path.join("folder_b", "b.jpg")],
        weights=[1.0, 1.0],
        cum_weights=[1.0, 2.0],
        folder_memory=folder_memory,
    )

    _ = next(provider)

    assert folder_memory.step == 0


def test_controlled_random_weighted_balanced_branch_buckets_share_recency():
    providers = ImageProviders()
    providers.current_provider_name = "controlled_random_weighted"
    folder_memory = FolderSelectionMemory()
    folder_memory.record_folder(os.path.join("root", "branch_a", "folder_1"))
    root = _FakeNode("root", 1)
    branch_a = _FakeNode(os.path.join("root", "branch_a"), 2, root)
    branch_b = _FakeNode(os.path.join("root", "branch_b"), 2, root)
    folder_1 = _FakeNode(os.path.join("root", "branch_a", "folder_1"), 3, branch_a)
    folder_2 = _FakeNode(os.path.join("root", "branch_a", "folder_2"), 3, branch_a)
    folder_3 = _FakeNode(os.path.join("root", "branch_b", "folder_3"), 3, branch_b)
    tree = _FakeTree(
        {
            os.path.join("root", "branch_a", "folder_1", "a.jpg"): folder_1,
            os.path.join("root", "branch_a", "folder_2", "b.jpg"): folder_2,
            os.path.join("root", "branch_b", "folder_3", "c.jpg"): folder_3,
        },
        {
            os.path.join("root", "branch_a", "folder_1"): folder_1,
            os.path.join("root", "branch_a", "folder_2"): folder_2,
            os.path.join("root", "branch_b", "folder_3"): folder_3,
        },
        {2: ("b", (0, 0))},
    )

    payload = providers.get_current_provider_status_payload(
        image_paths=[
            os.path.join("root", "branch_a", "folder_1", "a.jpg"),
            os.path.join("root", "branch_a", "folder_2", "b.jpg"),
            os.path.join("root", "branch_b", "folder_3", "c.jpg"),
        ],
        weights=[1.0, 1.0, 1.0],
        current_image_path=os.path.join("root", "branch_a", "folder_2", "b.jpg"),
        folder_memory=folder_memory,
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
    assert payload["seen_before"] is True
    assert payload["bucket"] == os.path.join("root", "branch_a")


def test_controlled_random_weighted_streak_penalty_discourages_repeat():
    providers = ImageProviders()
    image_paths = [
        os.path.join("big", "a.jpg"),
        os.path.join("small", "b.jpg"),
    ]
    weights = [4.0, 1.0]
    cum_weights = [4.0, 5.0]
    folder_memory = FolderSelectionMemory()
    folder_memory.record_folder("big")
    folder_memory.record_folder("big")
    folder_memory.record_folder("big")

    random.seed(0)
    provider = providers.image_provider_controlled_random_weighted(
        image_paths,
        weights=weights,
        cum_weights=cum_weights,
        folder_memory=folder_memory,
        gap_min=1,
        gap_max=4,
        alpha=0.0,
        repeat_penalty=1.0,
    )

    picks = [next(provider) for _ in range(30)]

    assert any(os.path.dirname(path) == "small" for path in picks)


def test_controlled_random_weighted_single_folder_ignores_streak_penalty():
    providers = ImageProviders()
    image_paths = [
        os.path.join("only", "a.jpg"),
        os.path.join("only", "b.jpg"),
    ]
    folder_memory = FolderSelectionMemory()
    folder_memory.record_folder("only")
    folder_memory.record_folder("only")
    folder_memory.record_folder("only")

    provider = providers.image_provider_controlled_random_weighted(
        image_paths,
        weights=[1.0, 1.0],
        cum_weights=[1.0, 2.0],
        folder_memory=folder_memory,
        gap_min=1,
        gap_max=4,
        alpha=0.0,
        repeat_penalty=1.0,
    )

    picks = [next(provider) for _ in range(5)]

    assert all(os.path.dirname(path) == "only" for path in picks)


def test_controlled_random_settings_scale_with_selection_units_not_image_count():
    providers = ImageProviders()
    one_bucket_many_images = SelectionScope.single_unit(
        node_key="root\\flat_site",
        image_paths=[f"site\\img_{i}.jpg" for i in range(100)],
        weights=[1.0] * 100,
    )
    ten_bucket_scope = _selection_scope_from_units(
        *[
            (
                f"root\\bucket_{i}",
                2,
                ("root", f"root\\bucket_{i}"),
                [f"bucket_{i}\\only.jpg"],
                [1.0],
            )
            for i in range(10)
        ]
    )

    one_bucket_settings = providers.get_controlled_random_settings(
        image_paths=one_bucket_many_images.image_paths,
        weights=one_bucket_many_images.weights,
        selection_scope=one_bucket_many_images,
        bucket_mode="folder_bucket",
    )
    ten_bucket_settings = providers.get_controlled_random_settings(
        image_paths=ten_bucket_scope.image_paths,
        weights=ten_bucket_scope.weights,
        selection_scope=ten_bucket_scope,
        bucket_mode="folder_bucket",
    )

    assert one_bucket_settings["gap_max"] < ten_bucket_settings["gap_max"]
    assert one_bucket_settings["alpha"] > ten_bucket_settings["alpha"]


def test_controlled_random_status_uses_flat_node_memory_key_for_images_from_different_folders():
    providers = ImageProviders()
    providers.current_provider_name = "controlled_random_weighted"
    selection_scope = SelectionScope.single_unit(
        node_key="root\\flat_site",
        image_paths=[
            os.path.join("site", "a", "one.jpg"),
            os.path.join("site", "b", "two.jpg"),
        ],
        weights=[1.0, 1.0],
    )
    folder_memory = FolderSelectionMemory()
    folder_memory.record_folder("root\\flat_site")

    payload = providers.get_current_provider_status_payload(
        image_paths=selection_scope.image_paths,
        weights=selection_scope.weights,
        selection_scope=selection_scope,
        current_image_path=os.path.join("site", "b", "two.jpg"),
        folder_memory=folder_memory,
        settings={
            "gap_min": 3,
            "gap_max": 10,
            "alpha": 0.01,
            "repeat_penalty": 0.1,
            "bucket_mode": "folder_bucket",
        },
    )

    assert payload is not None
    assert payload["memory_key"] == "root\\flat_site"
    assert payload["seen_before"] is True


def test_select_manager_uses_selection_scope_without_image_level_tree_resolution(monkeypatch):
    providers = ImageProviders()
    selection_scope = SelectionScope.single_unit(
        node_key="root\\flat_site",
        image_paths=[f"site\\img_{i}.jpg" for i in range(20)],
        weights=[1.0] * 20,
    )

    class _NoResolveTree:
        defaults = type("_Defaults", (), {"mode": {2: ("b", (0, 0))}})()
        built_mode = {2: ("b", (0, 0))}

        def resolve_node_for_image(self, image_path):
            raise AssertionError("selection_scope should avoid image-level tree resolution")

    monkeypatch.setattr(
        "enkan.plugables.ImageProviders.ImageCacheManager",
        lambda image_provider, current_image_index, background_preload=True, **kwargs: object(),
    )

    providers.select_manager(
        selection_scope.image_paths,
        provider_name="controlled_random_weighted",
        weights=selection_scope.weights,
        cum_weights=selection_scope.cum_weights,
        folder_memory=FolderSelectionMemory(),
        selection_scope=selection_scope,
        tree=_NoResolveTree(),
    )

    settings = providers.get_current_provider_settings()
    assert settings["bucket_mode"] == "balance_bucket"
