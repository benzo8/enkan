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
        self.current_provider_settings: dict[str, float | int | str] = {}
        self.current_provider_setting_overrides: dict[str, float | int | str] = {}

    def _controlled_random_bucket_for_folder(
        self,
        folder: str,
        bucket_mode: str = "folder_bucket",
        tree=None,
    ) -> str:
        if tree is None:
            return folder
        node = tree.find_node(folder, tree.path_lookup)
        if node is None:
            return folder
        return self._controlled_random_bucket_for_node(node, tree, bucket_mode)

    def _controlled_random_mode_map(self, tree) -> dict[int, object]:
        if tree is None:
            return {}
        return getattr(tree, "defaults", None).mode or getattr(tree, "built_mode", None) or {}

    def _controlled_random_target_level(self, node, tree, bucket_mode: str) -> int:
        if bucket_mode != "balance_bucket":
            return node.level
        mode_map = self._controlled_random_mode_map(tree)
        if not mode_map:
            return node.level
        return min(node.level, max(mode_map.keys()))

    def _controlled_random_bucket_for_node(self, node, tree, bucket_mode: str) -> str:
        target_level = self._controlled_random_target_level(node, tree, bucket_mode)
        bucket_node = node.ancestor_at_level(target_level) or node
        return bucket_node.name

    def _controlled_random_bucket_for_image(
        self,
        image_path: str,
        *,
        tree=None,
        bucket_mode: str = "folder_bucket",
    ) -> str:
        if tree is None:
            return os.path.dirname(image_path)
        node = tree.resolve_node_for_image(image_path)
        if node is None:
            return os.path.dirname(image_path)
        return self._controlled_random_bucket_for_node(node, tree, bucket_mode)

    def _controlled_random_bucket_maps(
        self,
        image_paths: list[str],
        bucket_mode: str = "folder_bucket",
        tree=None,
    ) -> tuple[dict[str, str], dict[str, list[str]], dict[str, list[str]], list[str]]:
        folder_to_bucket: dict[str, str] = {}
        bucket_to_folders: dict[str, list[str]] = {}
        bucket_to_paths: dict[str, list[str]] = {}
        ordered_buckets: list[str] = []

        for path in image_paths:
            folder = os.path.dirname(path)
            if not folder:
                continue
            bucket = self._controlled_random_bucket_for_image(
                path,
                tree=tree,
                bucket_mode=bucket_mode,
            )
            folder_to_bucket.setdefault(folder, bucket)
            if bucket not in bucket_to_folders:
                bucket_to_folders[bucket] = []
                bucket_to_paths[bucket] = []
                ordered_buckets.append(bucket)
            if folder not in bucket_to_folders[bucket]:
                bucket_to_folders[bucket].append(folder)
            bucket_to_paths[bucket].append(path)

        return folder_to_bucket, bucket_to_folders, bucket_to_paths, ordered_buckets

    def _controlled_random_bucket_memory_state(
        self,
        folder_memory,
        bucket_key: str,
        bucket_folders: list[str],
        *,
        tree=None,
        bucket_mode: str = "folder_bucket",
    ) -> tuple[bool, int, int]:
        if not hasattr(folder_memory, "last_seen_by_folder"):
            folder = bucket_folders[0] if bucket_folders else ""
            seen_before = folder_memory.has_seen(folder)
            distance = folder_memory.distance_for(folder)
            streak_len = folder_memory.streak_for(folder)
            return seen_before, distance, streak_len

        seen_steps = [
            folder_memory.last_seen_by_folder[folder]
            for folder in bucket_folders
            if folder in folder_memory.last_seen_by_folder
        ]
        seen_before = bool(seen_steps)
        if not seen_before:
            return False, folder_memory.step + 1, 0

        projected_step = folder_memory.step + 1
        distance = projected_step - max(seen_steps)
        streak_len = 0
        if hasattr(folder_memory, "recent_folders"):
            for folder in reversed(folder_memory.recent_folders):
                resolved_bucket = self._controlled_random_bucket_for_folder(
                    folder,
                    bucket_mode=bucket_mode,
                    tree=tree,
                )
                if resolved_bucket != bucket_key:
                    break
                streak_len += 1
        elif folder_memory.current_streak_folder in bucket_folders:
            streak_len = folder_memory.current_streak_length
        return True, distance, streak_len

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

    def get_current_provider_settings(self) -> dict[str, float | int | str]:
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
        tree = provider_kwargs.get("tree")
        overrides: dict[str, float | int | str] = {}
        if provider_name == self.current_provider_name:
            overrides.update(self.current_provider_setting_overrides)

        for key in ("gap_min", "gap_max", "alpha", "repeat_penalty", "bucket_mode"):
            if key in provider_kwargs:
                overrides[key] = provider_kwargs[key]

        settings = self.get_controlled_random_settings(
            image_paths=image_paths,
            weights=weights,
            gap_min=int(overrides.get("gap_min", 3)),
            repeat_penalty=float(overrides.get("repeat_penalty", 0.1)),
            bucket_mode=str(overrides.get("bucket_mode", "balance_bucket")),
            tree=tree,
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
        bucket_mode = str(status_payload.get("bucket_mode", "folder_bucket"))
        bucket_marker = "BB" if bucket_mode == "balance_bucket" else "FB"

        if display_mode == "friendly":
            if not seen_before:
                return f"{bucket_marker} NEW"
            if combined >= 1.75:
                return f"{bucket_marker} DUE"
            if combined >= 1.15:
                return f"{bucket_marker} WARM"
            if folder_factor < 0.75:
                return f"{bucket_marker} COOLING"
            return f"{bucket_marker} NEUTRAL"

        if display_mode == "useful":
            if not seen_before:
                return f"{bucket_marker} NEW S{streak_len} B{bias_pct:+.0f}%"
            return f"{bucket_marker} A{age} S{streak_len} B{bias_pct:+.0f}%"

        if not seen_before:
            return (
                f"{bucket_marker} NEW S{streak_len} F{folder_factor:.2f} U{boost:.2f} T{streak_factor:.2f} "
                f"X{combined:.2f} B{bias_pct:+.0f}%"
            )
        return (
            f"{bucket_marker} A{age} S{streak_len} F{folder_factor:.2f} U{boost:.2f} T{streak_factor:.2f} "
            f"X{combined:.2f} B{bias_pct:+.0f}%"
        )

    def get_controlled_random_settings(
        self,
        *,
        image_paths: list[str],
        weights: list[float],
        gap_min: int = 3,
        repeat_penalty: float = 0.1,
        bucket_mode: str = "balance_bucket",
        tree=None,
    ) -> dict[str, float | int | str]:
        _, bucket_to_folders, _, _ = self._controlled_random_bucket_maps(
            image_paths,
            bucket_mode=bucket_mode,
            tree=tree,
        )
        bucket_count = max(1, len(bucket_to_folders))
        gap_min = max(1, int(gap_min))
        gap_max = max(gap_min + 1, min(80, round(bucket_count * 1.5)))
        alpha = max(0.0025, min(0.03, 0.12 / bucket_count))
        return {
            "gap_min": gap_min,
            "gap_max": gap_max,
            "alpha": alpha,
            "repeat_penalty": max(0.0, min(float(repeat_penalty), 1.0)),
            "bucket_mode": bucket_mode,
        }

    def get_current_provider_status_payload(
        self,
        *,
        image_paths: list[str],
        weights: list[float],
        current_image_path: str | None,
        folder_memory,
        settings: dict[str, float | int | str] | None = None,
        target_image_path: str | None = None,
        tree=None,
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
        bucket_mode = str(
            (settings or self.current_provider_settings or {}).get(
                "bucket_mode",
                "balance_bucket",
            )
        )
        _, bucket_to_folders, _, _ = self._controlled_random_bucket_maps(
            image_paths,
            bucket_mode=bucket_mode,
            tree=tree,
        )
        bucket = self._controlled_random_bucket_for_image(
            image_path,
            tree=tree,
            bucket_mode=bucket_mode,
        )
        bucket_folders = bucket_to_folders.get(bucket, [folder])

        folder_base_totals: dict[str, float] = {}
        for path, weight in zip(image_paths, weights):
            path_folder = os.path.dirname(path)
            if not path_folder:
                continue
            folder_base_totals[path_folder] = folder_base_totals.get(
                path_folder, 0.0
            ) + weight
        bucket_base_total = sum(
            weight
            for path, weight in zip(image_paths, weights)
            if self._controlled_random_bucket_for_image(
                path,
                tree=tree,
                bucket_mode=bucket_mode,
            )
            == bucket
        )

        one_folder_only = len(bucket_to_folders) <= 1
        resolved_settings = (
            settings
            or self.current_provider_settings
            or self.get_controlled_random_settings(
                image_paths=image_paths,
                weights=weights,
                bucket_mode=bucket_mode,
                tree=tree,
            )
        )
        gap_min = max(0, int(resolved_settings["gap_min"]))
        gap_max = max(gap_min, int(resolved_settings["gap_max"]))
        alpha = float(resolved_settings["alpha"])
        repeat_penalty = max(
            0.0,
            min(float(resolved_settings["repeat_penalty"]), 1.0),
        )

        seen_before, distance, streak_len = self._controlled_random_bucket_memory_state(
            folder_memory,
            bucket,
            bucket_folders,
            tree=tree,
            bucket_mode=bucket_mode,
        )
        if not seen_before:
            distance = min(distance, gap_max)
        clamped_distance = min(distance, gap_max)

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

        base_total = bucket_base_total
        effective_total = base_total * combined
        bias_pct = ((combined - 1.0) * 100.0) if base_total > 0 else 0.0

        return {
            "folder": folder,
            "bucket": bucket,
            "bucket_mode": bucket_mode,
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
        bucket_mode="balance_bucket",
        tree=None,
        **kwargs,
    ):
        if not image_paths:
            return iter(())

        bucket_to_paths: dict[str, list[str]] = {}
        bucket_to_image_cum_weights: dict[str, list[float]] = {}
        bucket_base_totals: dict[str, float] = {}
        folder_to_bucket, bucket_to_folders, _, ordered_buckets = (
            self._controlled_random_bucket_maps(
                image_paths,
                bucket_mode=bucket_mode,
                tree=tree,
            )
        )
        for path, weight in zip(image_paths, weights):
            bucket = self._controlled_random_bucket_for_image(
                path,
                tree=tree,
                bucket_mode=bucket_mode,
            )
            if bucket not in bucket_to_paths:
                bucket_to_paths[bucket] = []
                bucket_to_image_cum_weights[bucket] = []
                bucket_base_totals[bucket] = 0.0
            bucket_to_paths[bucket].append(path)
            bucket_base_totals[bucket] += weight
            bucket_to_image_cum_weights[bucket].append(bucket_base_totals[bucket])
        gap_min = max(0, int(gap_min))
        if gap_max is None:
            gap_max = max(gap_min + 1, len(ordered_buckets))
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
                one_folder_only = len(ordered_buckets) <= 1
                bucket_weights: list[float] = []
                bucket_factors: dict[str, float] = {}
                for bucket in ordered_buckets:
                    seen_before, distance, streak_len = (
                        self._controlled_random_bucket_memory_state(
                            folder_memory,
                            bucket,
                            bucket_to_folders[bucket],
                            tree=tree,
                            bucket_mode=bucket_mode,
                        )
                    )
                    if not seen_before:
                        distance = min(distance, gap_max)
                    clamped_distance = min(distance, gap_max)

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
                    bucket_factors[bucket] = combined
                    bucket_weights.append(bucket_base_totals[bucket] * combined)

                if not any(bucket_weights):
                    path, idx = _fallback_pick()
                else:
                    cum_eff = list(accumulate(bucket_weights))
                    if cum_eff[-1] <= 0.0:
                        path, idx = _fallback_pick()
                    else:
                        x = random.random() * cum_eff[-1]
                        bucket_idx = bisect.bisect_left(cum_eff, x)
                        if bucket_idx >= len(ordered_buckets):
                            bucket_idx = len(ordered_buckets) - 1
                        bucket = ordered_buckets[bucket_idx]
                        bucket_paths = bucket_to_paths[bucket]
                        bucket_cum_weights = bucket_to_image_cum_weights[bucket]
                        y = random.random() * bucket_cum_weights[-1]
                        idx = bisect.bisect_left(bucket_cum_weights, y)
                        if idx >= len(bucket_paths):
                            idx = len(bucket_paths) - 1
                        path = bucket_paths[idx]

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
