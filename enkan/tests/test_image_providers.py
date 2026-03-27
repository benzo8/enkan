import os
import random

from enkan.plugables.ImageProviders import ImageProviders
from enkan.utils.tests import _resolve_test_provider


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

    random.seed(1)
    provider = providers.image_provider_controlled_random_weighted(
        image_paths,
        weights=weights,
        cum_weights=cum_weights,
        gap_min=3,
        gap_max=10,
        alpha=0.01,
        repeat_penalty=0.0,
    )

    picks = [next(provider) for _ in range(4)]
    folders = [os.path.dirname(path) for path in picks]

    assert len(set(folders[:3])) == 3
    assert folders[3] == folders[0]


def test_controlled_random_weighted_allows_single_folder_repeats():
    providers = ImageProviders()
    image_paths = [
        os.path.join("only", "a.jpg"),
        os.path.join("only", "b.jpg"),
    ]
    weights = [1.0, 3.0]
    cum_weights = [1.0, 4.0]

    random.seed(2)
    provider = providers.image_provider_controlled_random_weighted(
        image_paths,
        weights=weights,
        cum_weights=cum_weights,
        gap_min=5,
        gap_max=10,
        alpha=0.01,
        repeat_penalty=0.0,
    )

    picks = [next(provider) for _ in range(8)]

    assert all(os.path.dirname(path) == "only" for path in picks)
    assert len(picks) == 8
