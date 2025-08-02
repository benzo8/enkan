from PIL import Image

class ImageLoaders:
    def __init__(self):
        self.loaders = {
            "disk" : self.load_from_disk
        }
    
    def register_loader(self, name, func):
        self.loaders[name] = func
        
    def load_image(self, image_path, loader_name="disk", **kwargs):
        loader_func = self.loaders.get(loader_name)
        if not loader_func:
            raise ValueError(f"No such loader: {loader_name}")
        
        image = loader_func(image_path, **kwargs)
        return image

    def load_from_disk(self, path):
        with Image.open(path) as img:
            img_copy = img.copy()
        return img_copy
        
