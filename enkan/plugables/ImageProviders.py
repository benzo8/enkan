import bisect
import os
import random
import logging
from dataclasses import dataclass
from collections import deque
from itertools import accumulate
from typing import Any, Callable

from enkan.cache.ImageCacheManager import ImageCacheManager
from enkan.mySlideshow.StatusBar import (
    PROVIDER_BURST_DOTS_STATUS_KEY,
    PROVIDER_DETAIL_STATUS_KEY,
    StatusSink,
    build_provider_burst_dots_contribution,
    build_provider_detail_contribution,
    build_provider_label_contribution,
)
from enkan.tree.selection_scope import SelectionScope, SelectionUnit
from enkan.utils.utils import weighted_choice, images_from_path

logger: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderSpec:
    factory_name: str
    label: str


@dataclass(frozen=True)
class ControlledRandomIndex:
    ordered_buckets: tuple[str, ...]
    bucket_to_units: dict[str, tuple[SelectionUnit, ...]]
    bucket_to_unit_cum_weights: dict[str, tuple[float, ...]]
    bucket_to_memory_keys: dict[str, tuple[str, ...]]
    bucket_base_totals: dict[str, float]
    unit_to_bucket: dict[str, str]


@dataclass
class ProviderRuntimeContext:
    status_sink: StatusSink
    image_paths: list[str]
    weights: list[float]
    selection_scope: SelectionScope | None
    tree: Any
    folder_memory: Any
    seen_folders: set[str]
    resolve_memory_key_for_image: Callable[[str, dict[str, object] | None], str | None]
    resolve_memory_key_for_scope: Callable[[str | None], str | None]
    scope_records_once_per_folder: Callable[[], bool]
    sync_memory: Callable[[], None]


@dataclass(frozen=True)
class ProviderDisplayEvent:
    image_path: str
    record_history: bool = True
    provider_pick_meta: dict[str, object] | None = None
    previous_image_path: str | None = None


class _StatefulProviderIterator:
    __slots__ = ("_next_func", "last_pick_meta")

    def __init__(
        self,
        next_func: Callable[[], tuple[str, dict[str, Any] | None]],
    ) -> None:
        self._next_func = next_func
        self.last_pick_meta: dict[str, Any] | None = None

    def __iter__(self):
        return self

    def __next__(self) -> str:
        path, meta = self._next_func()
        self.last_pick_meta = meta
        return path


class ImageProviders:
    def __init__(self):
        self.manager = None
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
        self.runtime_context: ProviderRuntimeContext | None = None
        self.current_provider_status_payload: dict[str, float | int | str] | None = None
        self._last_burst_memory_token = None
        self._last_display_event: ProviderDisplayEvent | None = None
        self._controlled_random_index_cache: dict[
            tuple[int, str, int],
            ControlledRandomIndex,
        ] = {}

    def _controlled_random_ancestor_keys_for_node(self, node) -> tuple[str, ...]:
        keys: list[str] = []
        current = node
        while current is not None:
            keys.append(current.name)
            current = current.parent
        keys.reverse()
        return tuple(keys)

    def _controlled_random_fallback_selection_scope(
        self,
        image_paths: list[str],
        weights: list[float],
        tree=None,
    ) -> SelectionScope:
        if not image_paths:
            return SelectionScope.from_parts([], [], [])

        selection_units: list[SelectionUnit] = []
        current_node_key: str | None = None
        current_level = 1
        current_ancestor_keys: tuple[str, ...] = ()
        current_images: list[str] = []
        current_weights: list[float] = []
        current_start = 0

        def flush_current() -> None:
            nonlocal current_node_key
            if current_node_key is None:
                return
            selection_units.append(
                SelectionUnit(
                    node_key=current_node_key,
                    node_level=current_level,
                    ancestor_keys=current_ancestor_keys or (current_node_key,),
                    image_paths=list(current_images),
                    weights=list(current_weights),
                    cum_weights=list(accumulate(current_weights)),
                    base_total=sum(current_weights),
                    start_index=current_start,
                )
            )

        for index, (path, weight) in enumerate(zip(image_paths, weights)):
            node = tree.resolve_node_for_image(path) if tree is not None else None
            if node is not None:
                node_key = node.name
                node_level = node.level
                ancestor_keys = self._controlled_random_ancestor_keys_for_node(node)
            else:
                node_key = os.path.dirname(path) or path
                node_level = max(1, len([part for part in node_key.split(os.path.sep) if part]))
                ancestor_keys = (node_key,)

            if current_node_key != node_key:
                flush_current()
                current_node_key = node_key
                current_level = node_level
                current_ancestor_keys = ancestor_keys
                current_images = []
                current_weights = []
                current_start = index

            current_images.append(path)
            current_weights.append(weight)

        flush_current()
        return SelectionScope.from_parts(
            image_paths,
            weights,
            selection_units,
        )

    def _selection_scope_for_provider(
        self,
        *,
        image_paths: list[str],
        weights: list[float],
        selection_scope: SelectionScope | None = None,
        tree=None,
    ) -> SelectionScope:
        if selection_scope is not None:
            return selection_scope
        return self._controlled_random_fallback_selection_scope(
            image_paths=image_paths,
            weights=weights,
            tree=tree,
        )

    def _controlled_random_mode_map(self, tree) -> dict[int, object]:
        if tree is None:
            return {}
        return getattr(tree, "defaults", None).mode or getattr(tree, "built_mode", None) or {}

    def _controlled_random_balance_level(self, tree) -> int:
        mode_map = self._controlled_random_mode_map(tree)
        if not mode_map:
            return 0
        return max(mode_map.keys())

    def _controlled_random_bucket_for_unit(
        self,
        unit: SelectionUnit,
        *,
        bucket_mode: str = "folder_bucket",
        balance_level: int = 0,
    ) -> str:
        if bucket_mode != "balance_bucket" or balance_level <= 0:
            return unit.node_key
        target_level = min(unit.node_level, balance_level)
        return unit.ancestor_key_at_level(target_level)

    def _controlled_random_index(
        self,
        *,
        image_paths: list[str],
        weights: list[float],
        selection_scope: SelectionScope | None = None,
        bucket_mode: str = "folder_bucket",
        tree=None,
    ) -> ControlledRandomIndex:
        scope = self._selection_scope_for_provider(
            image_paths=image_paths,
            weights=weights,
            selection_scope=selection_scope,
            tree=tree,
        )
        balance_level = self._controlled_random_balance_level(tree)
        cache_key = (id(scope), bucket_mode, balance_level)
        cached = self._controlled_random_index_cache.get(cache_key)
        if cached is not None:
            return cached

        ordered_buckets: list[str] = []
        bucket_to_units: dict[str, list[SelectionUnit]] = {}
        bucket_to_memory_keys: dict[str, list[str]] = {}
        bucket_base_totals: dict[str, float] = {}
        unit_to_bucket: dict[str, str] = {}

        for unit in scope.selection_units:
            bucket = self._controlled_random_bucket_for_unit(
                unit,
                bucket_mode=bucket_mode,
                balance_level=balance_level,
            )
            unit_to_bucket[unit.node_key] = bucket
            if bucket not in bucket_to_units:
                ordered_buckets.append(bucket)
                bucket_to_units[bucket] = []
                bucket_to_memory_keys[bucket] = []
                bucket_base_totals[bucket] = 0.0
            bucket_to_units[bucket].append(unit)
            bucket_to_memory_keys[bucket].append(unit.node_key)
            bucket_base_totals[bucket] += unit.base_total

        bucket_to_unit_cum_weights = {
            bucket: tuple(accumulate(unit.base_total for unit in units))
            for bucket, units in bucket_to_units.items()
        }
        index = ControlledRandomIndex(
            ordered_buckets=tuple(ordered_buckets),
            bucket_to_units={
                bucket: tuple(units) for bucket, units in bucket_to_units.items()
            },
            bucket_to_unit_cum_weights=bucket_to_unit_cum_weights,
            bucket_to_memory_keys={
                bucket: tuple(memory_keys)
                for bucket, memory_keys in bucket_to_memory_keys.items()
            },
            bucket_base_totals=bucket_base_totals,
            unit_to_bucket=unit_to_bucket,
        )
        self._controlled_random_index_cache[cache_key] = index
        return index

    def _controlled_random_bucket_memory_state(
        self,
        folder_memory,
        bucket_key: str,
        bucket_memory_keys: tuple[str, ...],
        *,
        unit_to_bucket: dict[str, str],
    ) -> tuple[bool, int, int]:
        if not hasattr(folder_memory, "last_seen_by_folder"):
            memory_key = bucket_memory_keys[0] if bucket_memory_keys else bucket_key
            seen_before = folder_memory.has_seen(memory_key)
            distance = folder_memory.distance_for(memory_key)
            streak_len = folder_memory.streak_for(memory_key)
            return seen_before, distance, streak_len

        seen_steps = [
            folder_memory.last_seen_by_folder[memory_key]
            for memory_key in bucket_memory_keys
            if memory_key in folder_memory.last_seen_by_folder
        ]
        seen_before = bool(seen_steps)
        if not seen_before:
            return False, folder_memory.step + 1, 0

        projected_step = folder_memory.step + 1
        distance = projected_step - max(seen_steps)
        streak_len = 0
        if hasattr(folder_memory, "recent_folders"):
            for memory_key in reversed(folder_memory.recent_folders):
                if unit_to_bucket.get(memory_key) != bucket_key:
                    break
                streak_len += 1
        elif folder_memory.current_streak_folder in bucket_memory_keys:
            streak_len = folder_memory.current_streak_length
        return True, distance, streak_len

    def _controlled_random_effects(
        self,
        *,
        seen_before: bool,
        distance: int,
        streak_len: int,
        one_bucket_only: bool,
        gap_min: int,
        gap_max: int,
        alpha: float,
        repeat_penalty: float,
    ) -> tuple[int, float, float, float, float]:
        if not seen_before:
            distance = min(distance, gap_max)
        clamped_distance = min(distance, gap_max)

        if one_bucket_only:
            folder_factor = 1.0
        elif gap_min > 0 and distance < gap_min:
            folder_factor = repeat_penalty + (
                (1.0 - repeat_penalty) * (distance / gap_min)
            )
        else:
            folder_factor = 1.0

        extra = max(0.0, clamped_distance - 10)
        boost = 1.0 + alpha * extra * extra
        if one_bucket_only or not seen_before or streak_len <= 0:
            streak_factor = 1.0
        else:
            streak_factor = max(0.25, 0.75 ** max(0, streak_len - 1))
        combined = folder_factor * boost * streak_factor
        return distance, folder_factor, boost, streak_factor, combined

    def _pick_meta_for_index(
        self,
        selection_scope: SelectionScope | None,
        index: int,
    ) -> dict[str, Any] | None:
        meta: dict[str, Any] = {"index": index}
        if selection_scope is None:
            return meta
        memory_key = selection_scope.memory_key_for_index(index)
        if memory_key:
            meta["memory_key"] = memory_key
        return meta

    def resolve_memory_key_for_image(
        self,
        image_path: str,
        *,
        selection_scope: SelectionScope | None = None,
        tree=None,
    ) -> str:
        node = tree.resolve_node_for_image(image_path) if tree is not None else None
        if node is not None:
            if selection_scope is None or node.name in selection_scope.unit_key_set():
                return node.name
        if selection_scope is not None:
            unit_keys = selection_scope.unit_keys_for_image(image_path)
            if len(unit_keys) == 1:
                return unit_keys[0]
            if unit_keys:
                if node is not None and node.name in unit_keys:
                    return node.name
                return unit_keys[0]
        return os.path.dirname(image_path)

    def register_provider(self, name, func):
        self.providers[name] = func
        self.provider_specs.setdefault(name, ProviderSpec(func.__name__, name[0:3].upper()))

    def configure_runtime_context(self, context: ProviderRuntimeContext) -> None:
        self.runtime_context = context
        self.publish_current_provider_status()

    def clear_provider_runtime_state(self) -> None:
        self.current_provider_status_payload = None
        self._last_burst_memory_token = None
        self._last_display_event = None
        sink = self._status_sink()
        if sink is not None:
            sink.clear_contribution(PROVIDER_DETAIL_STATUS_KEY)
            sink.clear_contribution(PROVIDER_BURST_DOTS_STATUS_KEY)

    def _status_sink(self) -> StatusSink | None:
        context = self.runtime_context
        return context.status_sink if context is not None else None

    def publish_current_provider_status(self) -> None:
        sink = self._status_sink()
        if sink is None:
            return
        label = self.get_current_provider_label()
        provider_name = self.current_provider_name
        if provider_name == "burst":
            sink.set_contribution(build_provider_label_contribution(label, priority=100))
        else:
            sink.set_contribution(build_provider_label_contribution(label))
        if provider_name != "controlled_random_weighted":
            sink.clear_contribution(PROVIDER_DETAIL_STATUS_KEY)
        if provider_name != "burst":
            sink.clear_contribution(PROVIDER_BURST_DOTS_STATUS_KEY)

    def _publish_provider_detail(self, detail: str) -> None:
        sink = self._status_sink()
        if sink is None:
            return
        if detail:
            sink.set_contribution(build_provider_detail_contribution(detail))
        else:
            sink.clear_contribution(PROVIDER_DETAIL_STATUS_KEY)

    def _publish_burst_dots(self, full: int, total: int) -> None:
        sink = self._status_sink()
        if sink is None:
            return
        total = max(0, int(total))
        remaining = max(0, total - int(full))
        if total > 0:
            sink.set_contribution(
                build_provider_burst_dots_contribution(remaining, total)
            )
        else:
            sink.clear_contribution(PROVIDER_BURST_DOTS_STATUS_KEY)

    def on_media_displayed(self, event: ProviderDisplayEvent) -> None:
        context = self.runtime_context
        if context is None:
            return
        self._last_display_event = event
        self.publish_current_provider_status()
        provider_name = self.current_provider_name
        if provider_name == "controlled_random_weighted":
            self._handle_controlled_random_display(event, context)
        elif provider_name == "burst":
            self._handle_burst_display(event, context)
        elif provider_name in {"random", "weighted"}:
            self._record_display_memory(event, context)
        else:
            self._publish_provider_detail("")

    def _handle_controlled_random_display(
        self,
        event: ProviderDisplayEvent,
        context: ProviderRuntimeContext,
    ) -> None:
        payload = self._controlled_random_payload_for_event(event, context)
        self._publish_controlled_random_detail(payload)
        self._record_display_memory(event, context)

    def _controlled_random_payload_for_event(
        self,
        event: ProviderDisplayEvent,
        context: ProviderRuntimeContext,
    ) -> dict[str, float | int | str] | None:
        if (
            not event.record_history
            and event.image_path == event.previous_image_path
            and self.current_provider_status_payload is not None
        ):
            return self.current_provider_status_payload
        payload = self.get_current_provider_status_payload(
            image_paths=context.image_paths,
            weights=context.weights,
            selection_scope=context.selection_scope,
            current_image_path=event.image_path,
            target_image_path=event.image_path,
            folder_memory=context.folder_memory,
            current_pick_meta=event.provider_pick_meta,
            tree=context.tree,
        )
        self.current_provider_status_payload = payload
        return payload

    def _publish_controlled_random_detail(
        self,
        payload: dict[str, float | int | str] | None,
    ) -> None:
        self._publish_provider_detail(
            self.get_current_provider_status(
                display_mode=self.get_current_provider_display_mode(),
                status_payload=payload,
            )
        )

    def _handle_burst_display(
        self,
        event: ProviderDisplayEvent,
        context: ProviderRuntimeContext,
    ) -> None:
        meta = event.provider_pick_meta or {}
        burst_index = int(meta.get("burst_index", 0) or 0)
        burst_size = int(meta.get("burst_size", 0) or 0)
        self._publish_burst_dots(burst_index, burst_size)
        if not event.record_history:
            return
        burst_token = meta.get("burst_token")
        if burst_token is not None and burst_token == self._last_burst_memory_token:
            return
        self._last_burst_memory_token = burst_token
        folder = str(meta.get("burst_folder") or os.path.dirname(event.image_path))
        memory_key = context.resolve_memory_key_for_scope(folder)
        if not memory_key:
            return
        context.folder_memory.record_folder(memory_key)
        context.sync_memory()

    def _record_display_memory(
        self,
        event: ProviderDisplayEvent,
        context: ProviderRuntimeContext,
    ) -> None:
        if not event.record_history:
            return
        memory_key = context.resolve_memory_key_for_image(
            event.image_path,
            event.provider_pick_meta,
        )
        if not memory_key:
            return
        if context.scope_records_once_per_folder():
            if memory_key in context.seen_folders:
                return
            context.seen_folders.add(memory_key)
        context.folder_memory.record_folder(memory_key)
        context.sync_memory()

    def select_manager(self, image_paths, provider_name="sequential", **kwargs):
        provider_func = self.providers.get(provider_name)
        if not provider_func:
            raise ValueError(f"No such provider: {provider_name}")
        status_sink = kwargs.pop("status_sink", None)
        config = kwargs.pop("config", None)
        preserve_display_mode = provider_name == self.current_provider_name
        kwargs = self._resolve_provider_kwargs(
            image_paths=image_paths,
            provider_name=provider_name,
            provider_kwargs=kwargs,
        )

        image_provider = provider_func(image_paths, **kwargs)
        self.manager = ImageCacheManager(
            image_provider,
            kwargs.get("index", 0),
            status_sink=status_sink,
            config=config,
        )
        self.current_provider_name = provider_name
        if not preserve_display_mode:
            self.current_provider_display_mode_index = 0
        self.clear_provider_runtime_state()
        self.publish_current_provider_status()
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
        self.publish_current_provider_status()
        if self.current_provider_name == "controlled_random_weighted":
            context = self.runtime_context
            if self.current_provider_status_payload is None and context is not None:
                last_event = self._last_display_event
                if last_event is not None:
                    self.current_provider_status_payload = (
                        self._controlled_random_payload_for_event(last_event, context)
                    )
            self._publish_controlled_random_detail(self.current_provider_status_payload)
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
        selection_scope = provider_kwargs.get("selection_scope")
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
            selection_scope=selection_scope,
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
        selection_scope: SelectionScope | None = None,
        gap_min: int = 3,
        repeat_penalty: float = 0.1,
        bucket_mode: str = "balance_bucket",
        tree=None,
    ) -> dict[str, float | int | str]:
        index = self._controlled_random_index(
            image_paths=image_paths,
            weights=weights,
            selection_scope=selection_scope,
            bucket_mode=bucket_mode,
            tree=tree,
        )
        bucket_count = max(1, len(index.ordered_buckets))
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
        selection_scope: SelectionScope | None = None,
        current_image_path: str | None,
        folder_memory,
        settings: dict[str, float | int | str] | None = None,
        target_image_path: str | None = None,
        current_pick_meta: dict[str, Any] | None = None,
        tree=None,
    ) -> dict[str, float | int | str] | None:
        provider_name = self.current_provider_name
        if provider_name != "controlled_random_weighted":
            return None

        scope = self._selection_scope_for_provider(
            image_paths=image_paths,
            weights=weights,
            selection_scope=selection_scope,
            tree=tree,
        )
        image_path = target_image_path or current_image_path
        if not image_path or not scope.image_paths:
            return None

        bucket_mode = str(
            (settings or self.current_provider_settings or {}).get(
                "bucket_mode",
                "balance_bucket",
            )
        )
        index = self._controlled_random_index(
            image_paths=image_paths,
            weights=weights,
            selection_scope=scope,
            bucket_mode=bucket_mode,
            tree=tree,
        )
        memory_key = (
            str(current_pick_meta["memory_key"])
            if current_pick_meta is not None and "memory_key" in current_pick_meta
            else self.resolve_memory_key_for_image(
                image_path,
                selection_scope=scope,
                tree=tree,
            )
        )
        bucket = index.unit_to_bucket.get(memory_key, memory_key)
        bucket_memory_keys = index.bucket_to_memory_keys.get(bucket, (memory_key,))

        resolved_settings = (
            settings
            or self.current_provider_settings
            or self.get_controlled_random_settings(
                image_paths=image_paths,
                weights=weights,
                selection_scope=scope,
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
            bucket_memory_keys,
            unit_to_bucket=index.unit_to_bucket,
        )
        one_bucket_only = len(index.ordered_buckets) <= 1
        distance, folder_factor, boost, streak_factor, combined = (
            self._controlled_random_effects(
                seen_before=seen_before,
                distance=distance,
                streak_len=streak_len,
                one_bucket_only=one_bucket_only,
                gap_min=gap_min,
                gap_max=gap_max,
                alpha=alpha,
                repeat_penalty=repeat_penalty,
            )
        )

        base_total = index.bucket_base_totals.get(bucket, 0.0)
        effective_total = base_total * combined
        bias_pct = ((combined - 1.0) * 100.0) if base_total > 0 else 0.0

        return {
            "folder": os.path.dirname(image_path),
            "memory_key": memory_key,
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
        if provider_name is None:
            provider_name = self.current_provider_name or "sequential"
        new_manager = self.select_manager(image_paths, provider_name, **kwargs)
        new_manager.reset()
        return new_manager

    def image_provider_sequential(
        self,
        image_paths,
        index=0,
        selection_scope: SelectionScope | None = None,
        **kwargs,
    ):
        current_index = max(0, int(index or 0))

        def next_item() -> tuple[str, dict[str, Any] | None]:
            nonlocal current_index
            if current_index >= len(image_paths):
                raise StopIteration
            path = image_paths[current_index]
            meta = self._pick_meta_for_index(selection_scope, current_index)
            current_index += 1
            return path, meta

        return _StatefulProviderIterator(next_item)

    def image_provider_random(
        self,
        image_paths,
        selection_scope: SelectionScope | None = None,
        **kwargs,
    ):
        def next_item() -> tuple[str, dict[str, Any] | None]:
            index = random.randrange(len(image_paths))
            return image_paths[index], self._pick_meta_for_index(selection_scope, index)

        return _StatefulProviderIterator(next_item)

    def image_provider_weighted(
        self,
        image_paths,
        cum_weights,
        selection_scope: SelectionScope | None = None,
        **kwargs,
    ):
        def next_item() -> tuple[str, dict[str, Any] | None]:
            x = random.random() * cum_weights[-1]
            index = bisect.bisect_left(cum_weights, x)
            if index >= len(image_paths):
                index = len(image_paths) - 1
            return image_paths[index], self._pick_meta_for_index(selection_scope, index)

        return _StatefulProviderIterator(next_item)

    def image_provider_controlled_random_weighted(
        self,
        image_paths,
        weights,
        cum_weights,
        folder_memory,
        selection_scope: SelectionScope | None = None,
        gap_min=3,
        gap_max=None,
        alpha=None,
        repeat_penalty=0.1,
        bucket_mode="balance_bucket",
        tree=None,
        **kwargs,
    ):
        if not image_paths:
            return _StatefulProviderIterator(
                lambda: (_ for _ in ()).throw(StopIteration)
            )

        scope = self._selection_scope_for_provider(
            image_paths=image_paths,
            weights=weights,
            selection_scope=selection_scope,
            tree=tree,
        )
        index = self._controlled_random_index(
            image_paths=image_paths,
            weights=weights,
            selection_scope=scope,
            bucket_mode=bucket_mode,
            tree=tree,
        )

        gap_min = max(0, int(gap_min))
        if gap_max is None:
            gap_max = max(gap_min + 1, len(index.ordered_buckets))
        gap_max = max(gap_min, int(gap_max))
        if alpha is None:
            alpha = 0.01
        alpha = float(alpha)
        repeat_penalty = max(0.0, min(float(repeat_penalty), 1.0))

        def fallback_pick() -> tuple[str, dict[str, Any] | None]:
            x = random.random() * cum_weights[-1]
            selected_index = bisect.bisect_left(cum_weights, x)
            if selected_index >= len(image_paths):
                selected_index = len(image_paths) - 1
            return (
                image_paths[selected_index],
                self._pick_meta_for_index(scope, selected_index),
            )

        def next_item() -> tuple[str, dict[str, Any] | None]:
            one_bucket_only = len(index.ordered_buckets) <= 1
            bucket_weights: list[float] = []
            for bucket in index.ordered_buckets:
                seen_before, distance, streak_len = (
                    self._controlled_random_bucket_memory_state(
                        folder_memory,
                        bucket,
                        index.bucket_to_memory_keys[bucket],
                        unit_to_bucket=index.unit_to_bucket,
                    )
                )
                _, _, _, _, combined = self._controlled_random_effects(
                    seen_before=seen_before,
                    distance=distance,
                    streak_len=streak_len,
                    one_bucket_only=one_bucket_only,
                    gap_min=gap_min,
                    gap_max=gap_max,
                    alpha=alpha,
                    repeat_penalty=repeat_penalty,
                )
                bucket_weights.append(index.bucket_base_totals[bucket] * combined)

            if not any(bucket_weights):
                return fallback_pick()

            cum_eff = list(accumulate(bucket_weights))
            if cum_eff[-1] <= 0.0:
                return fallback_pick()

            x = random.random() * cum_eff[-1]
            bucket_index = bisect.bisect_left(cum_eff, x)
            if bucket_index >= len(index.ordered_buckets):
                bucket_index = len(index.ordered_buckets) - 1
            bucket = index.ordered_buckets[bucket_index]
            bucket_units = index.bucket_to_units[bucket]
            bucket_unit_cum_weights = index.bucket_to_unit_cum_weights[bucket]
            y = random.random() * bucket_unit_cum_weights[-1]
            unit_index = bisect.bisect_left(bucket_unit_cum_weights, y)
            if unit_index >= len(bucket_units):
                unit_index = len(bucket_units) - 1
            unit = bucket_units[unit_index]
            z = random.random() * unit.cum_weights[-1]
            local_index = bisect.bisect_left(unit.cum_weights, z)
            if local_index >= len(unit.image_paths):
                local_index = len(unit.image_paths) - 1
            global_index = unit.start_index + local_index
            return (
                unit.image_paths[local_index],
                {
                    "index": global_index,
                    "memory_key": unit.node_key,
                    "bucket": bucket,
                },
            )

        return _StatefulProviderIterator(next_item)

    def image_provider_folder_burst(
        self,
        image_paths,
        cum_weights,
        burst_size=5,
        index=0,
        **kwargs,
    ):
        class _BurstIterator:
            __slots__ = (
                "_gen",
                "reset_burst",
                "current_burst_folder",
                "current_burst_token",
                "current_burst_index",
                "current_burst_size",
                "last_pick_meta",
            )

            def __init__(self, gen, reset_func):
                self._gen = gen
                self.reset_burst = reset_func
                self.current_burst_folder = None
                self.current_burst_token = None
                self.current_burst_index = 0
                self.current_burst_size = 0
                self.last_pick_meta = None

            def __iter__(self):
                return self

            def __next__(self):
                path = next(self._gen)
                self.last_pick_meta = {
                    "burst_folder": self.current_burst_folder,
                    "burst_token": self.current_burst_token,
                    "burst_index": self.current_burst_index,
                    "burst_size": self.current_burst_size,
                }
                return path

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
        current_burst_size = 0
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
            nonlocal next_seed, drop_first_seed, burst_token, current_burst_size
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
                    current_burst_size = len(burst_items)
                    iterator.current_burst_size = current_burst_size
                    iterator.current_burst_index = 0
                    burst_queue.extend(burst_items)
                iterator.current_burst_index = current_burst_size - len(burst_queue) + 1
                yield burst_queue.popleft()

        def reset_burst():
            nonlocal next_seed, drop_first_seed, current_burst_size
            burst_queue.clear()
            next_seed = None
            drop_first_seed = False
            current_burst_size = 0
            iterator.current_burst_folder = None
            iterator.current_burst_token = None
            iterator.current_burst_index = 0
            iterator.current_burst_size = 0
            iterator.last_pick_meta = None

        iterator._gen = burst_generator()
        iterator.reset_burst = reset_burst
        return iterator
