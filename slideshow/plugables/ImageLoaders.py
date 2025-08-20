from PIL import Image

from typing import Callable, Any

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
        **kwargs
    ) -> Image.Image:
        loader_func: Callable[..., Any] | None = self.loaders.get(loader_name)
        if not loader_func:
            raise ValueError(f"No such loader: {loader_name}")
        
        image: Image.Image = loader_func(image_path, **kwargs)
        return image

    def load_from_disk(
        self, 
        path: str
    ) -> Image.Image:
        with Image.open(path) as img:
            img_copy = img.copy()
        return img_copy
        
