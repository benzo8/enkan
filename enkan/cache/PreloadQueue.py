from collections import deque

class PreloadQueue:
    """
    A FIFO queue of preloaded images with a maximum size.
    Each element is a {path: image_obj} dict.
    """

    def __init__(self, max_size: int):
        self.queue = deque(maxlen=max_size)
        self.lookup = set()  # For fast membership checks
        self.max_size = max_size

    def push(self, path, image_obj):
        """
        Push a new (path, image_obj) to the bottom of the queue.
        If the queue is full, the oldest item is automatically dropped.
        """
        if path in self.lookup:
            return False  # Avoid duplicates

        # If queue is full, remove oldest
        if len(self.queue) == self.max_size:
            oldest = self.queue.popleft()
            self.lookup.difference_update(oldest.keys())

        self.queue.append({path: image_obj})
        self.lookup.add(path)
        return True

    def pop(self):
        """
        Pop and return the top (oldest) item in the queue.
        Returns None if the queue is empty.
        """
        if not self.queue:
            return None
        item = self.queue.popleft()
        self.lookup.difference_update(item.keys())
        return item
    
    def discard(self, path):
        """
        Remove a specific path from the queue if present.
        Returns True if the path was removed, else False.
        """
        if path not in self.lookup:
            return False
        self.lookup.discard(path)
        new_queue = deque(maxlen=self.max_size)
        for item in self.queue:
            if path not in item:
                new_queue.append(item)
        self.queue = new_queue
        return True
    
    def clear(self):
        """Remove all items from the queue."""
        self.queue.clear()
        self.lookup.clear()

    def __contains__(self, path):
        return path in self.lookup

    def __len__(self):
        return len(self.queue)

    def items(self):
        """Return a list of all queued items in order."""
        return list(self.queue)

    def __repr__(self):
        return f"PreloadQueue({list(self.queue)})"
