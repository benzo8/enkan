import bisect
import os
import random
import logging
from dataclasses import dataclass
from collections import deque
from itertools import accumulate

from enkan.cache.ImageCacheManager import ImageCacheManager
from enkan.utils.utils import weighted_choice, images_from_path

logger: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderSpec:
    factory_name: str
    label: str


class ImageProviders:
    def __init__(self):
        self.manager = None
        # Provider registry: key → provider factory function
        self.providers = {
            "sequential": self.image_provider_sequential,
            "random": self.image_provider_random,
            "weighted": self.image_provider_weighted,
            "controlled_random_weighted": self.image_provider_controlled_random_weighted,
            "burst": self.image_provider_folder_burst,
        }
        self.provider_specs = {
            "sequential": ProviderSpec("image_provider_sequential", "SEQ"),
            "random": ProviderSpec("image_provider_random", "RND"),
            "weighted": ProviderSpec("image_provider_weighted", "WGT"),
            "controlled_random_weighted": ProviderSpec(
                "image_provider_controlled_random_weighted", "CRW"
            ),
            "burst": ProviderSpec("image_provider_folder_burst", "BUR"),
        }
        self.provider_display_modes = {
            "controlled_random_weighted": ("off", "friendly", "useful", "debug"),
        }
        self.current_provider_name = None
        self.current_provider_display_mode_index = 0
        self.current_provider_settings: dict[str, float | int] = {}
        self.current_provider_setting_overrides: dict[str, float | int] = {}

    def register_provider(self, name, func):
        self.providers[name] = func
        self.provider_specs.setdefault(name, ProviderSpec(func.__name__, name[0:3].upper()))

    def select_manager(self, image_paths, provider_name="sequential", **kwargs):
        # Look up provider by name
        provider_func = self.providers.get(provider_name)
        if not provider_func:
            raise ValueError(f"No such provider: {provider_name}")
        preserve_display_mode = provider_name == self.current_provider_name
        kwargs = self._resolve_provider_kwargs(
            image_paths=image_paths,
            provider_name=provider_name,
            provider_kwargs=kwargs,
        )

        # Each provider factory should accept image_paths and kwargs
        image_provider = provider_func(image_paths, **kwargs)
        self.manager = ImageCacheManager(
            image_provider,
            kwargs.get("index", 0),
            background_preload=kwargs.get("background_preload", True)
        )
        self.current_provider_name = provider_name
        if not preserve_display_mode:
            self.current_provider_display_mode_index = 0
        return self.manager
    
    def get_current_provider_name(self):
        return self.current_provider_name

    def get_current_provider_display_modes(self) -> tuple[str, ...]:
        if not self.current_provider_name:
            return ("off",)
        return self.provider_display_modes.get(self.current_provider_name, ("off",))

    def get_current_provider_display_mode(self) -> str:
        modes = self.get_current_provider_display_modes()
        return modes[self.current_provider_display_mode_index % len(modes)]

    def cycle_current_provider_display_mode(self) -> str:
        modes = self.get_current_provider_display_modes()
        self.current_provider_display_mode_index = (
            self.current_provider_display_mode_index + 1
        ) % len(modes)
        return modes[self.current_provider_display_mode_index]

    def get_current_provider_label(self) -> str:
        if not self.current_provider_name:
            return "-"
        spec = self.provider_specs.get(self.current_provider_name)
        if spec:
            return spec.label
        return self.current_provider_name[0:3].upper()

    def get_current_provider_settings(self) -> dict[str, float | int]:
        return dict(self.current_provider_settings)

    def _resolve_provider_kwargs(
        self,
        *,
        image_paths: list[str],
        provider_name: str,
        provider_kwargs: dict[str, object],
    ) -> dict[str, object]:
        if provider_name != "controlled_random_weighted":
            self.current_provider_settings = {}
            self.current_provider_setting_overrides = {}
            return provider_kwargs

        weights = list(provider_kwargs.get("weights", []))
        overrides: dict[str, float | int] = {}
        if provider_name == self.current_provider_name:
            overrides.update(self.current_provider_setting_overrides)

        for key in ("gap_min", "gap_max", "alpha", "repeat_penalty"):
            if key in provider_kwargs:
                overrides[key] = provider_kwargs[key]

        settings = self.get_controlled_random_settings(
            image_paths=image_paths,
            weights=weights,
            gap_min=int(overrides.get("gap_min", 3)),
            repeat_penalty=float(overrides.get("repeat_penalty", 0.1)),
        )
        if "gap_max" in overrides:
            settings["gap_max"] = max(
                int(settings["gap_min"]),
                int(overrides["gap_max"]),
            )
        if "alpha" in overrides:
            settings["alpha"] = float(overrides["alpha"])

        self.current_provider_settings = dict(settings)
        self.current_provider_setting_overrides = dict(overrides)
        return {
            **provider_kwargs,
            **settings,
        }

    def get_current_provider_status(
        self,
        *,
        display_mode: str = "off",
        status_payload: dict[str, float | int | str] | None = None,
    ) -> str:
        provider_name = self.current_provider_name
        if provider_name != "controlled_random_weighted":
            return ""
        if display_mode == "off" or status_payload is None:
            return ""

        age = int(status_payload["age"])
        seen_before = bool(status_payload["seen_before"])
        streak_len = int(status_payload["streak_len"])
        bias_pct = float(status_payload["bias_pct"])
        folder_factor = float(status_payload["folder_factor"])
        boost = float(status_payload["boost"])
        streak_factor = float(status_payload["streak_factor"])
        combined = float(status_payload["combined"])

        if display_mode == "friendly":
            if not seen_before:
                return "NEW"
            if combined >= 1.75:
                return "DUE"
            if combined >= 1.15:
                return "WARM"
            if folder_factor < 0.75:
                return "COOLING"
            return "NEUTRAL"

        if display_mode == "useful":
            if not seen_before:
                return f"NEW S{streak_len} B{bias_pct:+.0f}%"
            return f"A{age} S{streak_len} B{bias_pct:+.0f}%"

        if not seen_before:
            return (
                f"NEW S{streak_len} F{folder_factor:.2f} U{boost:.2f} T{streak_factor:.2f} "
                f"X{combined:.2f} B{bias_pct:+.0f}%"
            )
        return (
            f"A{age} S{streak_len} F{folder_factor:.2f} U{boost:.2f} T{streak_factor:.2f} "
            f"X{combined:.2f} B{bias_pct:+.0f}%"
        )

    def get_controlled_random_settings(
        self,
        *,
        image_paths: list[str],
        weights: list[float],
        gap_min: int = 3,
        repeat_penalty: float = 0.1,
    ) -> dict[str, float | int]:
        folder_count = max(
            1,
            len(
                {
                    os.path.dirname(path)
                    for path in image_paths
                    if os.path.dirname(path)
                }
            ),
        )
        gap_min = max(1, int(gap_min))
        gap_max = max(gap_min + 1, min(80, round(folder_count * 1.5)))
        alpha = max(0.0025, min(0.03, 0.12 / folder_count))
        return {
            "gap_min": gap_min,
            "gap_max": gap_max,
            "alpha": alpha,
            "repeat_penalty": max(0.0, min(float(repeat_penalty), 1.0)),
        }

    def get_current_provider_status_payload(
        self,
        *,
        image_paths: list[str],
        weights: list[float],
        current_image_path: str | None,
        folder_memory,
        settings: dict[str, float | int] | None = None,
        target_image_path: str | None = None,
    ) -> dict[str, float | int | str] | None:
        provider_name = self.current_provider_name
        if provider_name != "controlled_random_weighted":
            return None

        image_path = target_image_path or current_image_path
        if not image_path or not image_paths:
            return None
        folder = os.path.dirname(image_path)
        if not folder:
            return None

        folder_base_totals: dict[str, float] = {}
        for path, weight in zip(image_paths, weights):
            path_folder = os.path.dirname(path)
            if not path_folder:
                continue
            folder_base_totals[path_folder] = folder_base_totals.get(
                path_folder, 0.0
            ) + weight

        one_folder_only = len(folder_base_totals) <= 1
        resolved_settings = (
            settings
            or self.current_provider_settings
            or self.get_controlled_random_settings(
                image_paths=image_paths,
                weights=weights,
            )
        )
        gap_min = max(0, int(resolved_settings["gap_min"]))
        gap_max = max(gap_min, int(resolved_settings["gap_max"]))
        alpha = float(resolved_settings["alpha"])
        repeat_penalty = max(
            0.0,
            min(float(resolved_settings["repeat_penalty"]), 1.0),
        )

        seen_before = folder_memory.has_seen(folder)
        distance = folder_memory.distance_for(folder)
        if not seen_before:
            distance = min(distance, gap_max)
        clamped_distance = min(distance, gap_max)
        streak_len = folder_memory.streak_for(folder)

        if one_folder_only:
            folder_factor = 1.0
        elif gap_min > 0 and distance < gap_min:
            folder_factor = repeat_penalty + (
                (1.0 - repeat_penalty) * (distance / gap_min)
            )
        else:
            folder_factor = 1.0

        extra = max(0.0, clamped_distance - 10)
        boost = 1.0 + alpha * extra * extra
        if one_folder_only or not seen_before or streak_len <= 0:
            streak_factor = 1.0
        else:
            streak_factor = max(0.25, 0.75 ** max(0, streak_len - 1))
        combined = folder_factor * boost * streak_factor

        base_total = folder_base_totals.get(folder, 0.0)
        effective_total = base_total * combined
        bias_pct = ((combined - 1.0) * 100.0) if base_total > 0 else 0.0

        return {
            "folder": folder,
            "age": distance,
            "seen_before": seen_before,
            "streak_len": streak_len,
            "folder_factor": folder_factor,
            "boost": boost,
            "streak_factor": streak_factor,
            "combined": combined,
            "bias_pct": bias_pct,
            "base_total": base_total,
            "effective_total": effective_total,
        }
    
    def reset_manager(self, image_paths, provider_name=None, **kwargs):
        """
        Resets the current image manager with (potentially new) image_paths and provider.
        If provider_name is not specified, uses the current one.
        """
        if provider_name is None:
            provider_name = self.current_provider_name or "sequential"
        new_manager = self.select_manager(image_paths, provider_name, **kwargs)
        new_manager.reset()
        return new_manager
    
    def image_provider_sequential(self, image_paths, index=0, **kwargs):
        try:
            for path in image_paths[index:]:
                yield path
        except GeneratorExit:
            logger.debug("Sequential image provider closed unexpectedly.")
            return

    def image_provider_random(self, image_paths, **kwargs):
        try:
            while True:
                yield random.choice(image_paths)
        except GeneratorExit:
            logger.debug("Random image provider closed unexpectedly.")
            return

    def image_provider_weighted(self, image_paths, cum_weights, **kwargs):
        try:
            while True:
                yield weighted_choice(image_paths, cum_weights=cum_weights)
        except GeneratorExit:
            logger.debug("Weighted image provider closed unexpectedly.")
            return

    def image_provider_controlled_random_weighted(
        self,
        image_paths,
        weights,
        cum_weights,
        folder_memory,
        gap_min=3,
        gap_max=None,
        alpha=None,
        repeat_penalty=0.1,
        **kwargs,
    ):
        if not image_paths:
            return iter(())

        folder_to_paths: dict[str, list[str]] = {}
        folder_to_image_cum_weights: dict[str, list[float]] = {}
        folder_base_totals: dict[str, float] = {}
        ordered_folders: list[str] = []

        for path, weight in zip(image_paths, weights):
            folder = os.path.dirname(path)
            if folder not in folder_to_paths:
                ordered_folders.append(folder)
                folder_to_paths[folder] = []
                folder_to_image_cum_weights[folder] = []
                folder_base_totals[folder] = 0.0
            folder_to_paths[folder].append(path)
            folder_base_totals[folder] += weight
            folder_to_image_cum_weights[folder].append(folder_base_totals[folder])

        unique_folders = set(ordered_folders)
        gap_min = max(0, int(gap_min))
        if gap_max is None:
            gap_max = max(gap_min + 1, len(unique_folders))
        gap_max = max(gap_min, int(gap_max))
        if alpha is None:
            alpha = 0.01
        alpha = float(alpha)
        repeat_penalty = max(0.0, min(float(repeat_penalty), 1.0))

        def _fallback_pick():
            x = random.random() * cum_weights[-1]
            idx = bisect.bisect_left(cum_weights, x)
            if idx >= len(image_paths):
                idx = len(image_paths) - 1
            return image_paths[idx], idx

        try:
            while True:
                one_folder_only = len(unique_folders) <= 1
                folder_weights = []
                for folder in ordered_folders:
                    distance = folder_memory.distance_for(folder)
                    seen_before = folder_memory.has_seen(folder)
                    if not seen_before:
                        distance = min(distance, gap_max)
                    clamped_distance = min(distance, gap_max)
                    streak_len = folder_memory.streak_for(folder)

                    if one_folder_only:
                        folder_factor = 1.0
                    elif gap_min > 0 and distance < gap_min:
                        folder_factor = repeat_penalty + (
                            (1.0 - repeat_penalty) * (distance / gap_min)
                        )
                    else:
                        folder_factor = 1.0

                    extra = max(0.0, clamped_distance - 10)
                    boost = 1.0 + alpha * extra * extra
                    if one_folder_only or not seen_before or streak_len <= 0:
                        streak_factor = 1.0
                    else:
                        streak_factor = max(0.25, 0.75 ** max(0, streak_len - 1))
                    combined = folder_factor * boost * streak_factor
                    folder_weights.append(folder_base_totals[folder] * combined)

                if not any(folder_weights):
                    path, idx = _fallback_pick()
                else:
                    cum_eff = list(accumulate(folder_weights))
                    if cum_eff[-1] <= 0.0:
                        path, idx = _fallback_pick()
                    else:
                        x = random.random() * cum_eff[-1]
                        folder_idx = bisect.bisect_left(cum_eff, x)
                        if folder_idx >= len(ordered_folders):
                            folder_idx = len(ordered_folders) - 1
                        folder = ordered_folders[folder_idx]
                        folder_paths = folder_to_paths[folder]
                        folder_cum_weights = folder_to_image_cum_weights[folder]
                        y = random.random() * folder_cum_weights[-1]
                        idx = bisect.bisect_left(folder_cum_weights, y)
                        if idx >= len(folder_paths):
                            idx = len(folder_paths) - 1
                        path = folder_paths[idx]

                yield path
        except GeneratorExit:
            logger.debug("Controlled-random weighted image provider closed unexpectedly.")
            return

    def image_provider_folder_burst(self, image_paths, cum_weights, burst_size=5, index=0, **kwargs):
        import os
    
        class _BurstIterator:
            __slots__ = ("_gen", "reset_burst", "current_burst_folder", "current_burst_token")

            def __init__(self, gen, reset_func):
                self._gen = gen
                self.reset_burst = reset_func
                self.current_burst_folder = None
                self.current_burst_token = None
    
            def __iter__(self):
                return self
    
            def __next__(self):
                return next(self._gen)
    
        if not image_paths:
            return _BurstIterator(iter(()), lambda: None)
    
        burst_size = max(1, int(burst_size or 1))
        tree = kwargs.get("tree")
        filters = kwargs.get("filters")
        include_video = kwargs.get("include_video", False)
        ignored_files = kwargs.get("ignored_files")
    
        burst_queue: deque[str] = deque()
        folder_cache: dict[str, list[str]] = {}
        next_seed = None
        drop_first_seed = False
        burst_token = 0
        if isinstance(index, int) and 0 <= index < len(image_paths):
            next_seed = image_paths[index]
            drop_first_seed = True
    
        def folder_images(image_path: str) -> list[str]:
            folder = os.path.dirname(image_path)
            cached = folder_cache.get(folder)
            if cached is None:
                cached = images_from_path(
                    folder,
                    tree=tree,
                    include_video=include_video,
                    filters=filters,
                    ignored_files=ignored_files,
                )
                folder_cache[folder] = cached or []
            return cached or []
    
        def build_burst(seed_image: str, *, drop_seed: bool = False) -> list[str]:
            if not seed_image:
                return []
            candidates = folder_images(seed_image)
            if not candidates:
                return [] if drop_seed else [seed_image]
            others = [img for img in candidates if img != seed_image]
            random.shuffle(others)
            burst = [] if drop_seed else [seed_image]
            needed = max(0, burst_size - len(burst))
            burst.extend(others[:needed])
            return burst
    
        iterator = _BurstIterator(None, None)

        def burst_generator():
            nonlocal next_seed, drop_first_seed, burst_token
            try:
                while True:
                    if not burst_queue:
                        if next_seed is None:
                            next_seed = weighted_choice(image_paths, cum_weights=cum_weights)
                            drop_seed = False
                        else:
                            drop_seed = drop_first_seed
                        burst_items = build_burst(next_seed, drop_seed=drop_seed)
                        next_seed = None
                        drop_first_seed = False
                        if not burst_items:
                            continue
                        burst_token += 1
                        iterator.current_burst_folder = os.path.dirname(
                            burst_items[0] if burst_items else ""
                        )
                        iterator.current_burst_token = burst_token
                        burst_queue.extend(burst_items)
                    yield burst_queue.popleft()
            except GeneratorExit:
                logger.debug("Folder burst image provider closed unexpectedly.")
                return
    
        def reset_burst():
            nonlocal next_seed, drop_first_seed
            burst_queue.clear()
            next_seed = None
            drop_first_seed = False
            iterator.current_burst_folder = None
            iterator.current_burst_token = None

        iterator._gen = burst_generator()
        iterator.reset_burst = reset_burst
        return iterator
