from enkan.cache.HistoryManager import HistoryManager
from enkan.cache.ImageCacheManager import ImageCacheManager


def test_history_manager_snapshot_restore_preserves_navigation():
    manager = HistoryManager()
    manager.add("a.jpg")
    manager.add("b.jpg")
    manager.add("c.jpg")

    assert manager.back() == "b.jpg"
    snapshot = manager.snapshot()

    restored = HistoryManager()
    restored.restore(snapshot)

    assert restored.current() == "b.jpg"
    assert restored.back() == "a.jpg"
    assert restored.forward_step() == "b.jpg"


def test_image_cache_manager_restore_history_round_trip():
    cache_manager = ImageCacheManager(iter(()), 0, background_preload=False)
    cache_manager.history_manager.add("scope_a\\one.jpg")
    cache_manager.history_manager.add("scope_a\\two.jpg")
    cache_manager.history_manager.add("scope_b\\three.jpg")
    cache_manager.history_manager.back()

    snapshot = cache_manager.history_snapshot()
    cache_manager.reset()

    assert cache_manager.history_manager.current() is None

    cache_manager.restore_history(snapshot)

    assert cache_manager.history_manager.current() == "scope_a\\two.jpg"
    assert cache_manager.history_manager.back() == "scope_a\\one.jpg"


def test_history_manager_remove_ignores_missing_path():
    history = HistoryManager(max_length=5)
    history.add("one.jpg")
    history.add("two.jpg")

    history.remove("missing.jpg")
    history.remove("two.jpg")
    history.remove("two.jpg")

    assert list(history.history) == ["one.jpg"]
    assert history.current() == "one.jpg"
