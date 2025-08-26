import random
import logging

from enkan.cache.ImageCacheManager import ImageCacheManager
from enkan.utils.utils import weighted_choice

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
        
    def image_provider_folder_burst(self, image_paths, cum_weights, burst_size=5, **kwargs):
        from collections import defaultdict
        import os

        folder_to_images = defaultdict(list)
        for path in image_paths:
            folder = os.path.dirname(path)
            folder_to_images[folder].append(path)

        burst_images = []
        try:
            while True:
                if not burst_images:
                    # Pick a new random folder and prepare a burst
                    random_image = weighted_choice(image_paths, cum_weights=cum_weights)
                    folder = os.path.dirname(random_image)
                    images_in_folder = folder_to_images[folder]
                    images = images_in_folder[:]
                    random.shuffle(images)
                    burst_images = images[:burst_size]
                # Yield one image per call
                yield burst_images.pop(0)
        except GeneratorExit:
            logger.debug("Folder burst image provider closed unexpectedly.")
            return