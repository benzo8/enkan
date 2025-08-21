import logging

logger: logging.Logger = logging.getLogger("__name__")   

class Stack:
    def __init__(self, max_size=None):
        """
        Initialize a new Stack.

        Args:
            max_size (int, optional): The maximum number of items the stack can hold.
                                      If None, the stack size is unlimited.
        """
        self.max_size = max_size
        self.stack = []

    def push(self, root, listA, listB):
        """
        Push a pair of lists onto the stack.

        Args:
            listA (list): The first list to be pushed onto the stack.
            listB (list): The second list to be pushed onto the stack.
        """
        if self.max_size is None or len(self.stack) < self.max_size:
            self.stack.append((root, listA, listB))
        else:
            logger.debug("Stack is full. Cannot push more items.")

    def pop(self):
        """
        Pop the top pair of lists off the stack.

        Returns:
            tuple: A tuple containing the two lists that were on top of the stack.
        """
        if self.stack:
            return self.stack.pop()
        else:
            logger.debug("Stack is empty. Cannot pop items.")
            return None, None, None  # Return empty lists if the stack is empty

    def read_top(self, index=1):
        if self.stack:
            return self.stack[len(self.stack) - index][0]

    def clear(self):
        """Clear the stack."""
        self.stack.clear()

    def len(self):
        return len(self.stack)

    def is_empty(self):
        """Check if the stack is empty."""
        return len(self.stack) == 0

    def is_full(self):
        """Check if the stack is full."""
        if self.max_size is None:
            return False
        return len(self.stack) >= self.max_size

