from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FolderSelectionMemory:
    step: int = 0
    last_seen_by_folder: dict[str, int] = field(default_factory=dict)
    current_streak_folder: str | None = None
    current_streak_length: int = 0

    def record_folder(self, folder: str, amount: int = 1) -> None:
        amount = max(1, int(amount))
        self.step += amount
        self.last_seen_by_folder[folder] = self.step
        if folder == self.current_streak_folder:
            self.current_streak_length += 1
        else:
            self.current_streak_folder = folder
            self.current_streak_length = 1

    def distance_for(self, folder: str, current_step: int | None = None) -> int:
        projected_step = self.step + 1 if current_step is None else int(current_step)
        if folder not in self.last_seen_by_folder:
            return projected_step
        return projected_step - self.last_seen_by_folder[folder]

    def has_seen(self, folder: str) -> bool:
        return folder in self.last_seen_by_folder

    def streak_for(self, folder: str) -> int:
        if folder != self.current_streak_folder:
            return 0
        return self.current_streak_length

    def clear(self) -> None:
        self.step = 0
        self.last_seen_by_folder.clear()
        self.current_streak_folder = None
        self.current_streak_length = 0

    def copy(self) -> "FolderSelectionMemory":
        return FolderSelectionMemory(
            step=self.step,
            last_seen_by_folder=dict(self.last_seen_by_folder),
            current_streak_folder=self.current_streak_folder,
            current_streak_length=self.current_streak_length,
        )
