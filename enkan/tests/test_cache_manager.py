import threading
import time
from pathlib import Path

from PIL import Image

from enkan.cache.CachedVideoData import CachedVideoData
from enkan.cache.ImageCacheManager import ImageCacheManager
from enkan.cache.PreloadQueue import PreloadQueue, PreloadedMedia
from enkan.plugables.ImageLoaders import ImageLoaders


def test_preload_queue_uses_typed_items():
    queue = PreloadQueue(2)

    assert queue.push("a.jpg", "payload") is True
    item = queue.pop()

    assert isinstance(item, PreloadedMedia)
    assert item.path == "a.jpg"
    assert item.media == "payload"


def test_preload_queue_allows_duplicate_paths():
    queue = PreloadQueue(3)

    assert queue.push("dup.jpg", "one") is True
    assert queue.push("dup.jpg", "two") is True

    items = queue.items()
    assert [item.path for item in items] == ["dup.jpg", "dup.jpg"]


def test_cache_manager_skips_invalid_provider_media(monkeypatch):
    valid_image = Image.new("RGB", (1, 1))

    def fake_load(self, path, *args, **kwargs):
        if path.endswith("good.jpg"):
            return valid_image
        return None

    monkeypatch.setattr(ImageLoaders, "load_image", fake_load)
    manager = ImageCacheManager(iter(["bad.jpg", "good.jpg"]), 0, background_preload=False)

    image_path, image_obj = manager.get_next(record_history=False)

    assert image_path == "good.jpg"
    assert image_obj == valid_image
    assert "bad.jpg" not in manager.lru_cache
    assert "good.jpg" in manager.lru_cache


def test_cache_manager_preload_refill_preserves_duplicate_provider_picks(monkeypatch):
    monkeypatch.setattr(ImageCacheManager, "_load_media", lambda self, path: f"media:{path}")
    manager = ImageCacheManager(
        iter(["dup.jpg", "dup.jpg", "other.jpg"]),
        0,
        background_preload=False,
    )

    queued = manager.preload_queue.items()

    assert [item.path for item in queued] == ["dup.jpg", "dup.jpg", "other.jpg"]


def test_cache_manager_preloads_and_caches_videos(tmp_path: Path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video-bytes")

    manager = ImageCacheManager(iter([str(video_path)]), 0, background_preload=False)

    queued = manager.preload_queue.items()
    assert len(queued) == 1
    assert queued[0].path == str(video_path)
    assert isinstance(queued[0].media, CachedVideoData)
    assert queued[0].media.data == b"video-bytes"

    image_path, media_obj = manager.get_next(record_history=False)

    assert image_path == str(video_path)
    assert isinstance(media_obj, CachedVideoData)
    assert media_obj.data == b"video-bytes"
    assert str(video_path) in manager.lru_cache
    assert isinstance(manager.lru_cache.get(str(video_path)), CachedVideoData)
    assert manager.lru_cache.get(str(video_path)).is_memory_backed


def test_cache_manager_uses_path_backed_payload_for_oversized_videos(
    tmp_path: Path, monkeypatch
):
    video_path = tmp_path / "large.mp4"
    video_path.write_bytes(b"video-bytes")
    monkeypatch.setattr("enkan.cache.ImageCacheManager.constants.VIDEO_CACHE_MAX_BYTES", 1)

    manager = ImageCacheManager(iter([str(video_path)]), 0, background_preload=False)

    queued = manager.preload_queue.items()
    assert len(queued) == 1
    assert queued[0].path == str(video_path)
    assert isinstance(queued[0].media, CachedVideoData)
    assert queued[0].media.data is None
    assert queued[0].media.is_path_backed

    image_path, media_obj = manager.get_next(record_history=False)

    assert image_path == str(video_path)
    assert isinstance(media_obj, CachedVideoData)
    assert media_obj.data is None


def test_cache_manager_waits_for_starved_background_refill(monkeypatch):
    slow_media = CachedVideoData(path="slow.mp4", data=b"slow")
    second_media = Image.new("RGB", (1, 1))
    load_started = threading.Event()
    release_load = threading.Event()

    def fake_load(self, path):
        if path == "slow.mp4":
            load_started.set()
            release_load.wait(timeout=1.0)
            return slow_media
        return second_media

    monkeypatch.setattr(ImageCacheManager, "_load_media", fake_load)
    manager = ImageCacheManager(
        iter(["slow.mp4", "second.jpg"]),
        0,
        background_preload=True,
    )

    assert load_started.wait(timeout=1.0)

    result = {}
    done = threading.Event()

    def consumer():
        result["value"] = manager.get_next(record_history=False)
        done.set()

    thread = threading.Thread(target=consumer, daemon=True)
    thread.start()

    assert not done.wait(timeout=0.1)
    release_load.set()
    assert done.wait(timeout=1.0)
    thread.join(timeout=1.0)

    image_path, media_obj = result["value"]
    assert image_path == "slow.mp4"
    assert media_obj == slow_media


def test_cache_manager_serves_ready_items_while_refill_is_busy(monkeypatch):
    ready_media = Image.new("RGB", (1, 1))
    slow_media = CachedVideoData(path="slow.mp4", data=b"slow")
    slow_started = threading.Event()
    release_load = threading.Event()

    def fake_load(self, path):
        if path == "ready.jpg":
            return ready_media
        slow_started.set()
        release_load.wait(timeout=1.0)
        return slow_media

    monkeypatch.setattr(ImageCacheManager, "_load_media", fake_load)
    manager = ImageCacheManager(
        iter(["ready.jpg", "slow.mp4"]),
        0,
        background_preload=True,
    )

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if slow_started.is_set() and len(manager.preload_queue) == 1:
            break
        time.sleep(0.01)

    assert slow_started.is_set()
    assert len(manager.preload_queue) == 1

    start = time.monotonic()
    image_path, media_obj = manager.get_next(record_history=False)
    elapsed = time.monotonic() - start

    release_load.set()

    assert image_path == "ready.jpg"
    assert media_obj == ready_media
    assert elapsed < 0.15


def test_cache_manager_returns_none_for_invalid_explicit_path(monkeypatch):
    monkeypatch.setattr(ImageLoaders, "load_image", lambda self, path, *args, **kwargs: None)
    manager = ImageCacheManager(iter(()), 0, background_preload=False)

    image_path, image_obj = manager.get_next("missing.jpg", record_history=False)

    assert image_path is None
    assert image_obj is None
    assert "missing.jpg" not in manager.lru_cache


def test_cache_manager_skips_missing_image_when_loader_raises(monkeypatch):
    monkeypatch.setattr(
        ImageLoaders,
        "load_image",
        lambda self, path, *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError(path)),
    )
    manager = ImageCacheManager(iter(()), 0, background_preload=False)

    image_path, image_obj = manager.get_next("missing.jpg", record_history=False)

    assert image_path is None
    assert image_obj is None
    assert "missing.jpg" not in manager.lru_cache
