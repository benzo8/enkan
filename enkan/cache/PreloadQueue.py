from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PreloadedMedia:
    path: str
    media: Any
    meta: dict[str, Any] | None = None


class PreloadQueue:
    """
    A FIFO queue of preloaded media with a maximum size.
    Each element is a `PreloadedMedia` item.
    """

    def __init__(self, max_size: int):
        self.queue = deque(maxlen=max_size)
        self.lookup = set()  # For fast membership checks
        self.max_size = max_size

    def push(self, path, media, meta=None):
        """
        Push a new preloaded media item to the bottom of the queue.
        If the queue is full, the oldest item is automatically dropped.
        """
        if path in self.lookup:
            return False

        if len(self.queue) == self.max_size:
            oldest = self.queue.popleft()
            self.lookup.discard(oldest.path)

        self.queue.append(PreloadedMedia(path=path, media=media, meta=meta))
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
        self.lookup.discard(item.path)
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
            if item.path != path:
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
