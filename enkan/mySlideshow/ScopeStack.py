from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Generic, TypeVar

logger: logging.Logger = logging.getLogger(__name__)

StateT = TypeVar("StateT")


@dataclass(slots=True)
class ScopeStackEntry(Generic[StateT]):
    path: str | None
    image_paths: list[str]
    scope_state: StateT


class ScopeStack(Generic[StateT]):
    def __init__(self, max_size: int | None = None) -> None:
        self.max_size = max_size
        self._stack: list[ScopeStackEntry[StateT]] = []

    def push(self, entry: ScopeStackEntry[StateT]) -> bool:
        if self.is_full():
            logger.debug("Scope stack is full. Cannot push more items.")
            return False
        self._stack.append(entry)
        return True

    def pop(self) -> ScopeStackEntry[StateT] | None:
        if self.is_empty():
            logger.debug("Scope stack is empty. Cannot pop items.")
            return None
        return self._stack.pop()

    def peek(self, depth: int = 1) -> ScopeStackEntry[StateT] | None:
        if depth <= 0:
            raise ValueError("depth must be >= 1")
        if len(self._stack) < depth:
            return None
        return self._stack[-depth]

    def clear(self) -> None:
        self._stack.clear()

    def __len__(self) -> int:
        return len(self._stack)

    def is_empty(self) -> bool:
        return len(self._stack) == 0

    def is_full(self) -> bool:
        if self.max_size is None:
            return False
        return len(self._stack) >= self.max_size
