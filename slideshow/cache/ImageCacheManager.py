from slideshow.cache.LRUCache import LRUCache
from slideshow.cache.PreloadQueue import PreloadQueue
from slideshow.cache.HistoryManager import HistoryManager
from slideshow.utils.utils import is_videofile
from slideshow import constants


class ImageCacheManager:
    """
    Combines LRUCache, PreloadQueue, and HistoryManager
    to manage images and videos for the slideshow.
    """

    def __init__(self, image_provider, load_image_from_disk, debug=False):
        self.lru_cache = LRUCache(constants.CACHE_SIZE)
        self.preload_queue = PreloadQueue(constants.PRELOAD_QUEUE_LENGTH)
        self.history_manager = HistoryManager(constants.HISTORY_QUEUE_LENGTH)
        self.image_provider = image_provider
        self.load_image_from_disk = load_image_from_disk
        self.debug = debug

        # Initial preload
        # self._preload_refill()

    # -----------------------
    # Internal helpers
    # -----------------------
    
    def _log(self, message):
        """Print debug messages if debug mode is on."""
        if self.debug:
            print(f"[DEBUG] {message}")

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

    def _preload_refill(self):
        while len(self.preload_queue) < self.preload_queue.max_size:
            image_path = self.image_provider()
            if image_path is None:
                break
            if image_path in self.preload_queue:
                continue
            image_obj = self._load_image(image_path)
            self.preload_queue.push(image_path, image_obj)

    # -----------------------
    # Public API
    # -----------------------

    def get_next(self, image_path=None, record_history=True):
        """
        Retrieve the next (image_path, image_obj).
        If image_path is None, use PreloadQueue.
        Updates history if record_history=True.
        DEBUG: Prints where the image was loaded from (PreloadQueue, LRUCache, or Disk).
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
                    self._log("[DEBUG] No image provided (empty provider).")
                    return None, None
                image_obj = self._load_image(image_path)
                source = "Disk"
        else:
            # Check cache first
            image_obj = self.lru_cache.get(image_path)
            if image_obj:
                source = "LRUCache"
            else:
                image_obj = self._load_image(image_path)
                source = "Disk"

        # Step 2: Conditionally update history
        if record_history:
            self.history_manager.add(image_path)

        # Step 3: Refill preload
        self._preload_refill()

        # Step 4: Debug output
        self._log(f"Loaded: {image_path} (from {source})")

        return image_path, image_obj

    def back(self):
        """Navigate one step back in history."""
        path = self.history_manager.back()
        if path is None:
            return None, None
        return path, self._load_image(path)

    def forward(self):
        """Navigate one step forward in history."""
        path = self.history_manager.forward_step()
        if path is None:
            return None, None
        return path, self._load_image(path)

    def current(self):
        """Return the current image (path, image_obj) without moving."""
        path = self.history_manager.current()
        if path is None:
            return None, None
        return path, self._load_image(path)
    
    def reset(self):
        """
        Clear the LRUCache, PreloadQueue, and HistoryManager.
        Useful after changing image paths or toggling subfolder mode.
        """
        self.lru_cache.clear()
        self.preload_queue.clear()
        self.history_manager.clear()
        self._log("Cache, preload queue, and history cleared.")

    def __repr__(self):
        return (
            f"ImageCacheManager("
            f"cache={self.lru_cache}, "
            f"preload={self.preload_queue}, "
            f"history={self.history_manager})"
        )
