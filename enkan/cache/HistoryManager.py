from collections import deque
from enkan import constants

class HistoryManager:
    """
    A single-line history manager with back/forward navigation.
    Maintains a deque of visited paths with a current index pointer.
    """

    def __init__(self, max_length=constants.HISTORY_QUEUE_LENGTH):
        self.history = deque(maxlen=max_length)
        self.current_index = -1  # -1 = no current item
        self.max_length = max_length

    def add(self, path):
        """
        Add a new path. Clears forward history if the user
        has navigated backward and is now moving forward naturally.
        """
        # Remove everything after the current index (future)
        while len(self.history) - 1 > self.current_index:
            self.history.pop()

        # Add new path
        self.history.append(path)
        self.current_index = len(self.history) - 1
        
    def remove(self, path):
        """
        Remove a path from history, adjusting current_index if needed.
        If the current item is removed, current_index is moved to the previous item.
        """
        try:
            idx = self.history.index(path)
        except ValueError:
            return  # Path not in history

        self.history.remove(path)

        # Adjust current_index
        if idx < self.current_index:
            self.current_index -= 1
        elif idx == self.current_index:
            # Move to the previous item, or -1 if none exist
            self.current_index = max(0, self.current_index - 1) if self.history else -1

    def back(self):
        if self.current_index > 0:
            self.current_index -= 1
            return self.history[self.current_index]
        return None

    def forward_step(self):
        if self.current_index < len(self.history) - 1:
            self.current_index += 1
            return self.history[self.current_index]
        return None

    def current(self):
        """Return the current item (or None if empty)."""
        if self.current_index == -1:
            return None
        return self.history[self.current_index]

    def clear(self):
        self.history.clear()
        self.current_index = -1

    def __repr__(self):
        line = list(self.history)
        return f"HistoryManager(line={line}, current_index={self.current_index})"
