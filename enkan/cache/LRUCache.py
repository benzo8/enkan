from collections import OrderedDict

class LRUCache:
    """
    A simple LRU (Least Recently Used) cache implemented using OrderedDict.
    Keys are promoted to the front on access or insertion.
    """

    def __init__(self, max_size: int):
        self.cache = OrderedDict()
        self.max_size = max_size

    def put(self, key, value):
        if key in self.cache:
            # Update and promote
            self.cache.move_to_end(key, last=False)
            self.cache[key] = value
        else:
            self.cache[key] = value
            self.cache.move_to_end(key, last=False)
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=True)  # Remove oldest

    def get(self, key):
        if key not in self.cache:
            return None
        self.cache.move_to_end(key, last=False)
        return self.cache[key]
    
    def clear(self):
        """Remove all items from the cache."""
        self.cache.clear()

    def __contains__(self, key):
        return key in self.cache

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.put(key, value)

    def items(self):
        """Return items in most-recently-used order."""
        return list(self.cache.items())

    def __len__(self):
        return len(self.cache)

    def __repr__(self):
        return f"LRUCache({list(self.cache.items())})"
