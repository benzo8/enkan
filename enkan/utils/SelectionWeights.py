from __future__ import annotations

from dataclasses import dataclass
from itertools import accumulate


@dataclass
class SelectionWeights:
    weights: list[float]
    cum_weights: list[float]

    @classmethod
    def from_weights(cls, weights: list[float]) -> "SelectionWeights":
        return cls(list(weights), list(accumulate(weights)))

    @classmethod
    def from_parts(
        cls, weights: list[float], cum_weights: list[float]
    ) -> "SelectionWeights":
        return cls(list(weights), list(cum_weights))

    def copy(self) -> "SelectionWeights":
        return SelectionWeights.from_parts(self.weights, self.cum_weights)

    def provider_kwargs(self) -> dict[str, list[float]]:
        return {
            "weights": self.weights,
            "cum_weights": self.cum_weights,
        }

    def remove_at(self, index: int) -> None:
        self.weights.pop(index)
        self.cum_weights = list(accumulate(self.weights))
