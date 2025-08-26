from __future__ import annotations
from typing import Callable, Optional

import logging
from PIL import Image, UnidentifiedImageError

logger: logging.Logger = logging.getLogger("enkan.imageloaders")

class ImageLoaders:
    def __init__(self):
        self.loaders = {
            "disk" : self.load_from_disk
        }
    
    def register_loader(
        self, 
        name, 
        func
    ) -> None:
        self.loaders[name] = func
        
    def load_image(
        self,
        image_path: str,
        loader_name: str = "disk",
        suppress_errors: bool = True,
        **kwargs
    ) -> Optional[Image.Image]:
        loader_func: Callable[..., Image.Image | None] | None = self.loaders.get(loader_name)
        if not loader_func:
            if suppress_errors:
                logger.warning("No such loader '%s'", loader_name)
                return None
            raise ValueError(f"No such loader: {loader_name}")

        try:
            return loader_func(image_path, **kwargs)
        except Exception as e:
            # Never emit traceback unless higher-level debug wants it
            if suppress_errors:
                logger.info("Image load failed: %s (%s)", image_path, e)
                return None
            raise

    def load_from_disk(
        self, 
        path: str
    ) -> Image.Image | None:
        try:
            with Image.open(path) as img:
                return img.copy()
        except (FileNotFoundError, PermissionError) as e:
            logger.info("File access issue: %s (%s)", path, e)
        except UnidentifiedImageError as e:
            logger.info("Unidentified/corrupt image: %s (%s)", path, e)
        except OSError as e:
            logger.info("PIL OSError on %s (%s)", path, e)
        return None