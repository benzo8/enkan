import os
import random

from enkan.plugables.FolderSelectionMemory import FolderSelectionMemory
from enkan.plugables.ImageProviders import ImageProviders
from enkan.tree.diagnostics import _resolve_test_provider


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
