import threading
import logging

from PIL import Image

from .LRUCache import LRUCache
from .PreloadQueue import PreloadQueue
from .HistoryManager import HistoryManager
from enkan.plugables.ImageLoaders import ImageLoaders
from enkan.utils.utils import is_videofile
from enkan import constants

logger: logging.Logger = logging.getLogger("enkan.cache")     

class ImageCacheManager:
    """
    Combines LRUCache, PreloadQueue, and HistoryManager
    to manage images and videos for the slideshow.
    Supports background preloading of images.
    """

    def __init__(self, image_provider, current_image_index, background_preload=True):
        self.lru_cache = LRUCache(constants.CACHE_SIZE)
        self.preload_queue = PreloadQueue(constants.PRELOAD_QUEUE_LENGTH)
        self.history_manager = HistoryManager(constants.HISTORY_QUEUE_LENGTH)
        self.image_provider = image_provider
        self.image_loader = ImageLoaders()
        self.current_image_index = current_image_index
        self.background_preload = background_preload

        self._lock = threading.Lock()
        self._refill_thread = None
        self._provider_lock = threading.Lock()

        # Initial preload (async if background=True)
        if self.background_preload:
            self._background_refill()
        else:
            self._preload_refill()

    # -----------------------
    # Preload
    # -----------------------

    def _provider_next(self) -> str:
        """Thread-safe wrapper around the image provider."""
        with self._provider_lock:
            return next(self.image_provider)

    def _preload_refill(self) -> None:
        """Fill preload queue fully."""
        while len(self.preload_queue) < self.preload_queue.max_size:
            try:
                image_path: str = self._provider_next()
            except StopIteration:
                break  # For linear/sequential provider; random providers never stop
            if image_path is None:
                break
            if image_path in self.preload_queue:
                continue
            image_obj: Image.Image = self._load_image(image_path)
            self.preload_queue.push(image_path, image_obj)
            logger.debug(f"Preloaded: {image_path}")

    def _background_refill(self):
        """Start a background refill thread if not already running."""
        with self._lock:
            if self._refill_thread and self._refill_thread.is_alive():
                logger.debug("Background refill aborted. Already refilling.")
                return  # Already refilling
            self._refill_thread = threading.Thread(
                target=self._preload_refill, daemon=True
            )
            self._refill_thread.start()
            logger.debug("Background refill started.")

    # -----------------------
    # Image Loading
    # -----------------------

    def _load_image(self, image_path: str) -> Image.Image | None:
        if is_videofile(image_path):
            return None
        image_obj: Image.Image = self.lru_cache.get(image_path)
        if image_obj is None:
            logger.debug(f"Loading from Disk: {image_path}")
            image_obj: Image.Image = self.image_loader.load_image(image_path)
            self.lru_cache.put(image_path, image_obj)
        else:
            logger.debug(f"Loaded from LRUCache: {image_path}")
        return image_obj

    # -----------------------
    # Public API
    # -----------------------

    def get_next(
        self, 
        image_path: str = None, 
        record_history: bool = True
    ) -> tuple[str | None, Image.Image | None]:
        """
        Retrieve the next (image_path, image_obj).
        If image_path is None, pop from PreloadQueue.
        Updates history if record_history=True.
        """
        image_obj: Image.Image = None
        source: str = None

        # Step 1: Pop from preload if no explicit path is given
        if image_path is None:
            popped = self.preload_queue.pop()
            if popped:
                image_path, image_obj = next(iter(popped.items()))
                source = "PreloadQueue"
            else:
                try:
                    image_path = self._provider_next()
                except StopIteration:
                    logger.debug("No image provided (empty provider).")
                    return None, None
                image_obj = self._load_image(image_path)
                source = "Disk"
        else:
            image_obj = self.lru_cache.get(image_path)
            if image_obj:
                source = "LRUCache"
            else:
                image_obj = self._load_image(image_path)
                source = "Disk"

        # Step 2: Conditionally update history
        if record_history:
            self.history_manager.add(image_path)

        # Step 3: Refill preload (in background if enabled)
        if self.background_preload:
            self._background_refill()
        else:
            self._preload_refill()

        # Step 4: Debug output
        logger.debug(f"Loaded: {image_path} (from {source})")

        return image_path, image_obj

    def back(self):
        path = self.history_manager.back()
        if path is None:
            return None, None
        return path, self._load_image(path)

    def forward(self):
        path = self.history_manager.forward_step()
        if path is None:
            return None, None
        return path, self._load_image(path)

    def current(self):
        path = self.history_manager.current()
        if path is None:
            return None, None
        return path, self._load_image(path)

    def reset(self):
        """Clear all caches and history."""
        self.lru_cache.clear()
        self.preload_queue.clear()
        self.history_manager.clear()
        logger.debug("Cache, preload queue, and history cleared.")

        if self.background_preload:
            self._background_refill()
        else:
            self._preload_refill()

    def reset_provider(self) -> bool:
        """Reset provider-specific state and clear pending preloads."""
        reset_callable = getattr(self.image_provider, "reset_burst", None)
        if not callable(reset_callable):
            return False
        with self._provider_lock:
            reset_callable()
        self.preload_queue.clear()
        if self.background_preload:
            self._background_refill()
        else:
            self._preload_refill()
        logger.debug("Provider state reset; preload queue cleared.")
        return True

    def __repr__(self):
        return (
            f"ImageCacheManager("
            f"cache={self.lru_cache}, "
            f"preload={self.preload_queue}, "
            f"history={self.history_manager})"
        )
