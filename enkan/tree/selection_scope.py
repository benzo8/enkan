from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from itertools import accumulate


@dataclass
class SelectionUnit:
    node_key: str
    node_level: int
    ancestor_keys: tuple[str, ...]
    image_paths: list[str]
    weights: list[float]
    cum_weights: list[float]
    base_total: float
    start_index: int = 0

    @property
    def end_index(self) -> int:
        return self.start_index + len(self.image_paths)

    def ancestor_key_at_level(self, target_level: int) -> str:
        if not self.ancestor_keys:
            return self.node_key
        level_index = max(0, min(int(target_level), len(self.ancestor_keys)) - 1)
        return self.ancestor_keys[level_index]

    def contains_index(self, index: int) -> bool:
        return self.start_index <= index < self.end_index

    def contains_image(self, image_path: str) -> bool:
        return image_path in self.image_paths

    def copy(self) -> "SelectionUnit":
        return SelectionUnit(
            node_key=self.node_key,
            node_level=self.node_level,
            ancestor_keys=tuple(self.ancestor_keys),
            image_paths=list(self.image_paths),
            weights=list(self.weights),
            cum_weights=list(self.cum_weights),
            base_total=self.base_total,
            start_index=self.start_index,
        )

    def remove_local_index(self, local_index: int) -> bool:
        if local_index < 0 or local_index >= len(self.image_paths):
            return False
        self.image_paths.pop(local_index)
        self.weights.pop(local_index)
        self.cum_weights = list(accumulate(self.weights))
        self.base_total = sum(self.weights)
        return True


@dataclass
class SelectionScope:
    image_paths: list[str]
    weights: list[float]
    cum_weights: list[float]
    selection_units: list[SelectionUnit]
    _unit_starts: list[int] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.cum_weights and self.weights:
            self.cum_weights = list(accumulate(self.weights))
        self._rebuild_unit_starts()

    @classmethod
    def from_parts(
        cls,
        image_paths: list[str],
        weights: list[float],
        selection_units: list[SelectionUnit] | None = None,
        cum_weights: list[float] | None = None,
    ) -> "SelectionScope":
        return cls(
            image_paths=list(image_paths),
            weights=list(weights),
            cum_weights=list(cum_weights) if cum_weights is not None else list(accumulate(weights)),
            selection_units=[unit.copy() for unit in selection_units or []],
        )

    @classmethod
    def single_unit(
        cls,
        *,
        node_key: str,
        image_paths: list[str],
        weights: list[float],
        node_level: int = 1,
        ancestor_keys: tuple[str, ...] | None = None,
    ) -> "SelectionScope":
        ancestor_keys = ancestor_keys or (node_key,)
        selection_unit = SelectionUnit(
            node_key=node_key,
            node_level=node_level,
            ancestor_keys=tuple(ancestor_keys),
            image_paths=list(image_paths),
            weights=list(weights),
            cum_weights=list(accumulate(weights)),
            base_total=sum(weights),
            start_index=0,
        )
        return cls.from_parts(
            image_paths,
            weights,
            [selection_unit],
        )

    def _rebuild_unit_starts(self) -> None:
        self._unit_starts = [unit.start_index for unit in self.selection_units]

    def copy(self) -> "SelectionScope":
        return SelectionScope.from_parts(
            self.image_paths,
            self.weights,
            self.selection_units,
            self.cum_weights,
        )

    def unit_for_index(self, index: int) -> SelectionUnit | None:
        if index < 0 or index >= len(self.image_paths) or not self.selection_units:
            return None
        position = bisect_right(self._unit_starts, index) - 1
        if position < 0:
            return None
        unit = self.selection_units[position]
        if unit.contains_index(index):
            return unit
        return None

    def memory_key_for_index(self, index: int) -> str | None:
        unit = self.unit_for_index(index)
        if unit is None:
            return None
        return unit.node_key

    def unit_key_set(self) -> set[str]:
        return {unit.node_key for unit in self.selection_units}

    def unit_keys_for_image(self, image_path: str) -> list[str]:
        return [
            unit.node_key
            for unit in self.selection_units
            if unit.contains_image(image_path)
        ]

    def remove_at(self, index: int) -> None:
        if index < 0 or index >= len(self.image_paths):
            return

        target_unit = self.unit_for_index(index)
        self.image_paths.pop(index)
        self.weights.pop(index)
        self.cum_weights = list(accumulate(self.weights))

        if target_unit is None:
            return

        local_index = index - target_unit.start_index
        target_unit.remove_local_index(local_index)

        remove_unit_index = None
        for unit_index, unit in enumerate(self.selection_units):
            if unit is target_unit:
                remove_unit_index = unit_index
                break

        if remove_unit_index is None:
            self._rebuild_unit_starts()
            return

        shift_from_index = remove_unit_index + 1
        if not target_unit.image_paths:
            self.selection_units.pop(remove_unit_index)
            shift_from_index = remove_unit_index

        for unit in self.selection_units[shift_from_index:]:
            unit.start_index -= 1

        self._rebuild_unit_starts()
