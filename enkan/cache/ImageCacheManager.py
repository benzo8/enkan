import os
import threading
import logging

from PIL import Image

from .LRUCache import LRUCache
from .PreloadQueue import PreloadQueue
from .HistoryManager import HistoryManager
from .CachedVideoData import CachedVideoData
from enkan.plugables.ImageLoaders import ImageLoaders
from enkan.utils.utils import is_videofile
from enkan import constants
from enkan.mySlideshow.StatusBar import (
    StatusSink,
    build_cache_dots_contribution,
)

logger: logging.Logger = logging.getLogger("enkan.cache")     

class ImageCacheManager:
    """
    Combines LRUCache, PreloadQueue, and HistoryManager
    to manage images and videos for the slideshow.
    Supports background preloading of images.
    """

    def __init__(
        self,
        image_provider,
        current_image_index,
        background_preload=True,
        status_sink: StatusSink | None = None,
    ):
        self.lru_cache = LRUCache(constants.CACHE_SIZE)
        self.preload_queue = PreloadQueue(constants.PRELOAD_QUEUE_LENGTH)
        self.history_manager = HistoryManager(constants.HISTORY_QUEUE_LENGTH)
        self.image_provider = image_provider
        self.image_loader = ImageLoaders()
        self.current_image_index = current_image_index
        self.background_preload = background_preload
        self.current_media_metadata = None
        self.status_sink = status_sink

        self._lock = threading.RLock()
        self._queue_state = threading.Condition(self._lock)
        self._refill_thread = None
        self._refill_active = False
        self._provider_lock = threading.Lock()

        # Initial preload (async if background=True)
        if self.background_preload:
            self._background_refill()
        else:
            self._preload_refill()
        self._publish_cache_dots_status()

    def _publish_cache_dots_status(self) -> None:
        status_sink = self.status_sink
        if status_sink is None:
            return
        with self._queue_state:
            full = len(self.preload_queue)
            total = self.preload_queue.max_size
        status_sink.set_contribution(build_cache_dots_contribution(full, total))

    # -----------------------
    # Preload
    # -----------------------

    def _provider_next(self) -> str:
        """Thread-safe wrapper around the image provider."""
        with self._provider_lock:
            return next(self.image_provider)

    def _provider_pick_meta(self) -> dict[str, object] | None:
        return getattr(self.image_provider, "last_pick_meta", None)

    def _preload_refill(self) -> None:
        """Fill preload queue fully."""
        try:
            while True:
                with self._queue_state:
                    if len(self.preload_queue) >= self.preload_queue.max_size:
                        break

                try:
                    image_path: str = self._provider_next()
                except StopIteration:
                    break  # For linear/sequential provider; random providers never stop

                if image_path is None:
                    break
                provider_meta = self._provider_pick_meta()

                media = self._load_media(image_path)

                with self._queue_state:
                    if media is None:
                        logger.debug("Skipping invalid preload candidate: %s", image_path)
                        self._queue_state.notify_all()
                        continue
                    self.preload_queue.push(image_path, media, meta=provider_meta)
                    self._queue_state.notify_all()
                    logger.debug("Preloaded: %s", image_path)
                self._publish_cache_dots_status()
        finally:
            with self._queue_state:
                self._refill_active = False
                self._refill_thread = None
                self._queue_state.notify_all()
            self._publish_cache_dots_status()

    def _background_refill(self):
        """Start a background refill thread if not already running."""
        with self._queue_state:
            if self._refill_active and self._refill_thread and self._refill_thread.is_alive():
                logger.debug("Background refill aborted. Already refilling.")
                return  # Already refilling
            self._refill_active = True
            self._refill_thread = threading.Thread(
                target=self._preload_refill, daemon=True
            )
            self._refill_thread.start()
            logger.debug("Background refill started.")

    # -----------------------
    # Image Loading
    # -----------------------

    def _load_media(self, image_path: str) -> Image.Image | CachedVideoData | None:
        with self._queue_state:
            if image_path in self.lru_cache:
                logger.debug("Loaded from LRUCache: %s", image_path)
                return self.lru_cache.get(image_path)

        logger.debug("Loading from Disk: %s", image_path)
        if is_videofile(image_path):
            if not os.path.exists(image_path):
                logger.info("Video path missing: %s", image_path)
                return None
            try:
                if constants.VIDEO_CACHE_POLICY == "cache-all":
                    with open(image_path, "rb") as handle:
                        media = CachedVideoData(path=image_path, data=handle.read())
                else:
                    video_size = os.path.getsize(image_path)
                    if video_size <= constants.VIDEO_CACHE_MAX_BYTES:
                        with open(image_path, "rb") as handle:
                            media = CachedVideoData(path=image_path, data=handle.read())
                    else:
                        logger.debug(
                            "Video exceeds byte-cache limit (%s > %s): %s",
                            video_size,
                            constants.VIDEO_CACHE_MAX_BYTES,
                            image_path,
                        )
                        media = CachedVideoData(path=image_path)
            except OSError as exc:
                logger.warning("Failed to read video into cache: %s", image_path, exc_info=exc)
                return None

            with self._queue_state:
                if image_path in self.lru_cache:
                    return self.lru_cache.get(image_path)
                self.lru_cache.put(image_path, media)
            return media

        try:
            image_obj: Image.Image | None = self.image_loader.load_image(image_path)
        except FileNotFoundError:
            logger.info("Image path missing during load: %s", image_path)
            return None
        except PermissionError:
            logger.info("Image path unavailable during load: %s", image_path)
            return None
        except OSError as exc:
            logger.info("Image load OS error for %s: %s", image_path, exc)
            return None
        if image_obj is not None:
            with self._queue_state:
                if image_path in self.lru_cache:
                    return self.lru_cache.get(image_path)
                self.lru_cache.put(image_path, image_obj)
        return image_obj

    def _pop_preloaded(self):
        with self._queue_state:
            item = self.preload_queue.pop()
        if item is not None:
            self._publish_cache_dots_status()
        return item

    def _wait_for_preloaded(self):
        item = None
        with self._queue_state:
            if len(self.preload_queue) > 0:
                item = self.preload_queue.pop()
            elif not self._refill_active:
                return None
            else:
                logger.debug("Preload queue starved; waiting for refill to produce media.")
                while len(self.preload_queue) == 0 and self._refill_active:
                    self._queue_state.wait()

                if len(self.preload_queue) > 0:
                    item = self.preload_queue.pop()

        if item is not None:
            self._publish_cache_dots_status()
        return item

    # -----------------------
    # Public API
    # -----------------------

    def get_next(
        self, 
        image_path: str = None, 
        record_history: bool = True
    ) -> tuple[str | None, Image.Image | CachedVideoData | None]:
        """
        Retrieve the next (image_path, media_obj).
        If image_path is None, pop from PreloadQueue.
        Updates history if record_history=True.
        """
        media_obj: Image.Image | CachedVideoData | None = None
        source: str = None
        provider_meta: dict[str, object] | None = None
        self.current_media_metadata = None

        # Step 1: Pop from preload if no explicit path is given
        if image_path is None:
            while True:
                popped = self._pop_preloaded()
                if popped is None and self.background_preload:
                    popped = self._wait_for_preloaded()

                if popped:
                    image_path = popped.path
                    media_obj = popped.media
                    provider_meta = popped.meta
                    source = "PreloadQueue"
                    break
                try:
                    image_path = self._provider_next()
                except StopIteration:
                    logger.debug("No image provided (empty provider).")
                    self.current_media_metadata = None
                    return None, None
                provider_meta = self._provider_pick_meta()
                media = self._load_media(image_path)
                if media is None:
                    logger.debug("Skipping invalid media from provider: %s", image_path)
                    image_path = None
                    continue
                media_obj = media
                source = "Disk"
                break
        else:
            with self._queue_state:
                cached = image_path in self.lru_cache
            media = self._load_media(image_path)
            if media is None:
                logger.debug("Requested media is no longer valid: %s", image_path)
                self.current_media_metadata = None
                return None, None
            media_obj = media
            provider_meta = None
            source = "LRUCache" if cached else "Disk"

        # Step 2: Conditionally update history
        if record_history and image_path is not None:
            self.history_manager.add(image_path)

        # Step 3: Refill preload (in background if enabled)
        if self.background_preload:
            self._background_refill()
        else:
            self._preload_refill()
        self._publish_cache_dots_status()

        # Step 4: Debug output
        self.current_media_metadata = provider_meta
        logger.debug("Loaded: %s (from %s)", image_path, source)

        return image_path, media_obj

    def back(self):
        path = self.history_manager.back()
        if path is None:
            return None, None
        media = self._load_media(path)
        if media is None:
            return None, None
        return path, media

    def forward(self):
        path = self.history_manager.forward_step()
        if path is None:
            return None, None
        media = self._load_media(path)
        if media is None:
            return None, None
        return path, media

    def current(self):
        path = self.history_manager.current()
        if path is None:
            return None, None
        media = self._load_media(path)
        if media is None:
            return None, None
        return path, media

    def reset(self):
        """Clear all caches and history."""
        with self._queue_state:
            self.lru_cache.clear()
            self.preload_queue.clear()
            self._queue_state.notify_all()
        self._publish_cache_dots_status()
        self.history_manager.clear()
        logger.debug("Cache, preload queue, and history cleared.")

        if self.background_preload:
            self._background_refill()
        else:
            self._preload_refill()
        self._publish_cache_dots_status()

    def reset_provider(self) -> bool:
        """Reset provider-specific state and clear pending preloads."""
        reset_callable = getattr(self.image_provider, "reset_burst", None)
        if not callable(reset_callable):
            return False
        with self._provider_lock:
            reset_callable()
        with self._queue_state:
            self.preload_queue.clear()
            self._queue_state.notify_all()
        self._publish_cache_dots_status()
        if self.background_preload:
            self._background_refill()
        else:
            self._preload_refill()
        self._publish_cache_dots_status()
        logger.debug("Provider state reset; preload queue cleared.")
        return True

    def refresh_provider(self) -> None:
        """Discard queued provider output and refill using the current provider state."""
        with self._queue_state:
            self.preload_queue.clear()
            self._queue_state.notify_all()
        self._publish_cache_dots_status()
        if self.background_preload:
            self._background_refill()
        else:
            self._preload_refill()
        self._publish_cache_dots_status()
        logger.debug("Provider queue refreshed.")

    def invalidate(self, image_path: str) -> None:
        """Remove a specific path from caches and preload queue."""
        with self._queue_state:
            self.lru_cache.pop(image_path)
            self.preload_queue.discard(image_path)
            self._queue_state.notify_all()
        self._publish_cache_dots_status()

    def history_snapshot(self) -> dict[str, object]:
        return self.history_manager.snapshot()

    def restore_history(self, snapshot: dict[str, object] | None) -> None:
        self.history_manager.restore(snapshot)

    def __repr__(self):
        return (
            f"ImageCacheManager("
            f"cache={self.lru_cache}, "
            f"preload={self.preload_queue}, "
            f"history={self.history_manager})"
        )
