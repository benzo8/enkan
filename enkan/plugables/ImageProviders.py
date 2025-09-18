import random
import logging
from collections import deque

from enkan.cache.ImageCacheManager import ImageCacheManager
from enkan.utils.utils import weighted_choice, images_from_path

logger: logging.Logger = logging.getLogger("__name__")  

class ImageProviders:
    def __init__(self):
        self.manager = None
        # Provider registry: key → provider factory function
        self.providers = {
            "sequential": self.image_provider_sequential,
            "random": self.image_provider_random,
            "weighted": self.image_provider_weighted,
            "burst": self.image_provider_folder_burst
        }
        self.current_provider_name = None

    def register_provider(self, name, func):
        self.providers[name] = func

    def select_manager(self, image_paths, provider_name="sequential", **kwargs):
        # Look up provider by name
        provider_func = self.providers.get(provider_name)
        if not provider_func:
            raise ValueError(f"No such provider: {provider_name}")

        # Each provider factory should accept image_paths and kwargs
        image_provider = provider_func(image_paths, **kwargs)
        self.manager = ImageCacheManager(
            image_provider,
            kwargs.get("index", 0),
            background_preload=kwargs.get("background_preload", True)
        )
        self.current_provider_name = provider_name
        return self.manager
    
    def get_current_provider_name(self):
        return self.current_provider_name
    
    def reset_manager(self, image_paths, provider_name=None, **kwargs):
        """
        Resets the current image manager with (potentially new) image_paths and provider.
        If provider_name is not specified, uses the current one.
        """
        if provider_name is None:
            provider_name = self.current_provider_name or "sequential"
        new_manager = self.select_manager(image_paths, provider_name, **kwargs)
        new_manager.reset()
        return new_manager
    
    def image_provider_sequential(self, image_paths, index=0, **kwargs):
        try:
            for path in image_paths[index:]:
                yield path
        except GeneratorExit:
            logger.debug("Sequential image provider closed unexpectedly.")
            return

    def image_provider_random(self, image_paths, **kwargs):
        try:
            while True:
                yield random.choice(image_paths)
        except GeneratorExit:
            logger.debug("Random image provider closed unexpectedly.")
            return

    def image_provider_weighted(self, image_paths, cum_weights, **kwargs):
        try:
            while True:
                yield weighted_choice(image_paths, cum_weights=cum_weights)
        except GeneratorExit:
            logger.debug("Weighted image provider closed unexpectedly.")
            return
        



    def image_provider_folder_burst(self, image_paths, cum_weights, burst_size=5, index=0, **kwargs):
        import os
    
        class _BurstIterator:
            __slots__ = ("_gen", "reset_burst")
    
            def __init__(self, gen, reset_func):
                self._gen = gen
                self.reset_burst = reset_func
    
            def __iter__(self):
                return self
    
            def __next__(self):
                return next(self._gen)
    
        if not image_paths:
            return _BurstIterator(iter(()), lambda: None)
    
        burst_size = max(1, int(burst_size or 1))
        tree = kwargs.get("tree")
        filters = kwargs.get("filters")
        include_video = kwargs.get("include_video", False)
        ignored_files = kwargs.get("ignored_files")
    
        burst_queue: deque[str] = deque()
        folder_cache: dict[str, list[str]] = {}
        next_seed = None
        drop_first_seed = False
        if isinstance(index, int) and 0 <= index < len(image_paths):
            next_seed = image_paths[index]
            drop_first_seed = True
    
        def folder_images(image_path: str) -> list[str]:
            folder = os.path.dirname(image_path)
            cached = folder_cache.get(folder)
            if cached is None:
                cached = images_from_path(
                    folder,
                    tree=tree,
                    include_video=include_video,
                    filters=filters,
                    ignored_files=ignored_files,
                )
                folder_cache[folder] = cached or []
            return cached or []
    
        def build_burst(seed_image: str, *, drop_seed: bool = False) -> list[str]:
            if not seed_image:
                return []
            candidates = folder_images(seed_image)
            if not candidates:
                return [] if drop_seed else [seed_image]
            others = [img for img in candidates if img != seed_image]
            random.shuffle(others)
            burst = [] if drop_seed else [seed_image]
            needed = max(0, burst_size - len(burst))
            burst.extend(others[:needed])
            return burst
    
        def burst_generator():
            nonlocal next_seed, drop_first_seed
            try:
                while True:
                    if not burst_queue:
                        if next_seed is None:
                            next_seed = weighted_choice(image_paths, cum_weights=cum_weights)
                            drop_seed = False
                        else:
                            drop_seed = drop_first_seed
                        burst_items = build_burst(next_seed, drop_seed=drop_seed)
                        next_seed = None
                        drop_first_seed = False
                        if not burst_items:
                            continue
                        burst_queue.extend(burst_items)
                    yield burst_queue.popleft()
            except GeneratorExit:
                logger.debug("Folder burst image provider closed unexpectedly.")
                return
    
        def reset_burst():
            nonlocal next_seed, drop_first_seed
            burst_queue.clear()
            next_seed = None
            drop_first_seed = False
    
        return _BurstIterator(burst_generator(), reset_burst)
