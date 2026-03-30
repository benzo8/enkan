from __future__ import annotations

import os
import random
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from enkan.plugables.FolderSelectionMemory import FolderSelectionMemory
from enkan.plugables.ImageProviders import ImageProviders
from enkan.utils.SelectionWeights import SelectionWeights


def _run_provider(provider, folder_memory: FolderSelectionMemory | None, picks: int) -> float:
    start = time.perf_counter()
    for _ in range(picks):
        image_path = next(provider)
        if folder_memory is not None:
            folder_memory.record_folder(os.path.dirname(image_path))
    return time.perf_counter() - start


def main() -> None:
    providers = ImageProviders()
    picks = 2000
    folder_count = 100
    print(f"CRW scaling benchmark: {picks} picks, {folder_count} folders")
    print("images | weighted_s | crw_s | crw/weighted")
    print("-------+------------+-------+-------------")

    for image_count in (100, 1000, 5000, 10000):
        image_paths = [
            os.path.join(f"folder_{idx % folder_count}", f"{idx}.jpg")
            for idx in range(image_count)
        ]
        selection_weights = SelectionWeights.from_weights([1.0] * image_count)

        random.seed(0)
        weighted_provider = providers.image_provider_weighted(
            image_paths,
            cum_weights=selection_weights.cum_weights,
        )
        weighted_seconds = _run_provider(weighted_provider, None, picks)

        random.seed(0)
        folder_memory = FolderSelectionMemory()
        crw_provider = providers.image_provider_controlled_random_weighted(
            image_paths,
            weights=selection_weights.weights,
            cum_weights=selection_weights.cum_weights,
            folder_memory=folder_memory,
            gap_min=3,
            gap_max=50,
            alpha=0.01,
            repeat_penalty=0.1,
        )
        crw_seconds = _run_provider(crw_provider, folder_memory, picks)
        ratio = crw_seconds / weighted_seconds if weighted_seconds else float("inf")

        print(
            f"{image_count:>6} | {weighted_seconds:>10.4f} | {crw_seconds:>5.4f} | {ratio:>11.1f}"
        )


if __name__ == "__main__":
    main()
