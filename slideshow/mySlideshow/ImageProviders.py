import random
from slideshow.cache.ImageCacheManager import ImageCacheManager

class ImageProviders:
    def __init__(self, load_image_from_disk):
        self.load_image_from_disk = load_image_from_disk
        self.manager = None
        # Provider registry: key → provider factory function
        self.providers = {
            "sequential": self.image_provider_sequential,
            "random": self.image_provider_random,
            "weighted": self.image_provider_weighted,
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
            self.load_image_from_disk,
            kwargs.get("index", 0),
            debug=True,
            background_preload=False,
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
        return self.select_manager(image_paths, provider_name, **kwargs)
    
    def image_provider_sequential(self, image_paths, index=0, **kwargs):
        for path in image_paths[index:]:
            yield path

    def image_provider_random(self, image_paths, **kwargs):
        while True:
            yield random.choice(image_paths)

    def image_provider_weighted(self, image_paths, weights=None, **kwargs):
        while True:
            yield random.choices(image_paths, weights=weights, k=1)[0]