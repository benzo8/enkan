import threading
from slideshow.cache.LRUCache import LRUCache
from slideshow.cache.PreloadQueue import PreloadQueue
from slideshow.cache.HistoryManager import HistoryManager
from slideshow.utils.utils import is_videofile
from slideshow import constants


class ImageCacheManager:
    """
    Combines LRUCache, PreloadQueue, and HistoryManager
    to manage images and videos for the slideshow.
    Supports background preloading of images.
    """

    def __init__(self, image_provider, load_image_from_disk, current_image_index, debug=False, background_preload=True):
        self.lru_cache = LRUCache(constants.CACHE_SIZE)
        self.preload_queue = PreloadQueue(constants.PRELOAD_QUEUE_LENGTH)
        self.history_manager = HistoryManager(constants.HISTORY_QUEUE_LENGTH)
        self.image_provider = image_provider
        self.load_image_from_disk = load_image_from_disk
        self.current_image_index = current_image_index
        self.debug = debug
        self.background_preload = background_preload

        self._lock = threading.Lock()
        self._refill_thread = None

        # Initial preload (async if background_preload=True)
        if self.background_preload:
            self._background_refill()
        else:
            self._preload_refill()

    # -----------------------
    # Logging
    # -----------------------

    def _log(self, message):
        if self.debug:
            print(f"[DEBUG] {message}")

    # -----------------------
    # Preload
    # -----------------------

    def _preload_refill(self):
        """Fill preload queue fully."""
        preload_index = self.current_image_index + 1
        while len(self.preload_queue) < self.preload_queue.max_size:
            image_path = self.image_provider(index=preload_index)
            if image_path is None:
                break
            if image_path in self.preload_queue:
                preload_index += 1
                continue
            image_obj = self._load_image(image_path)
            self.preload_queue.push(image_path, image_obj)
            self._log(f"Preloaded: {image_path}")
            preload_index += 1
        self.current_image_index = preload_index - 1

    def _background_refill(self):
        """Start a background refill thread if not already running."""
        with self._lock:
            if self._refill_thread and self._refill_thread.is_alive():
                self._log("Background refill aborted. Already refilling.")
                return  # Already refilling
            self._refill_thread = threading.Thread(
                target=self._preload_refill, daemon=True
            )
            self._refill_thread.start()
            self._log("Background refill started.")

    # -----------------------
    # Image Loading
    # -----------------------

    def _load_image(self, image_path):
        if is_videofile(image_path):
            return None
        image_obj = self.lru_cache.get(image_path)
        if image_obj is None:
            self._log(f"Loading from Disk: {image_path}")
            image_obj = self.load_image_from_disk(image_path)
            self.lru_cache.put(image_path, image_obj)
        else:
            self._log(f"Loaded from LRUCache: {image_path}")
        return image_obj

    # -----------------------
    # Public API
    # -----------------------

    def get_next(self, image_path=None, record_history=True):
        """
        Retrieve the next (image_path, image_obj).
        If image_path is None, pop from PreloadQueue.
        Updates history if record_history=True.
        """
        image_obj = None
        source = None

        # Step 1: Pop from preload if no explicit path is given
        if image_path is None:
            popped = self.preload_queue.pop()
            if popped:
                image_path, image_obj = next(iter(popped.items()))
                source = "PreloadQueue"
            else:
                image_path = self.image_provider()
                if image_path is None:
                    self._log("No image provided (empty provider).")
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
        self._log(f"Loaded: {image_path} (from {source})")

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
        self._log("Cache, preload queue, and history cleared.")

        if self.background_preload:
            self._background_refill()
        else:
            self._preload_refill()

    def __repr__(self):
        return (
            f"ImageCacheManager("
            f"cache={self.lru_cache}, "
            f"preload={self.preload_queue}, "
            f"history={self.history_manager})"
        )