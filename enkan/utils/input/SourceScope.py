from __future__ import annotations

from dataclasses import dataclass

from enkan.utils.Defaults import Defaults
from enkan.utils.Filters import Filters


@dataclass(frozen=True)
class SourceScope:
    """
    Explicit per-source runtime scope used while ingesting/building one input.

    A SourceScope isolates txt-file globals and filter mutations from the shared
    runtime Defaults/Filters while preserving top-level CLI precedence.
    """

    defaults: Defaults
    filters: Filters

    @classmethod
    def from_runtime(cls, defaults: Defaults, filters: Filters) -> "SourceScope":
        return cls(
            defaults=defaults.clone_for_source(),
            filters=filters.clone_for_source(),
        )
