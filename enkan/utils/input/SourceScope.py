from __future__ import annotations

from dataclasses import dataclass

from enkan.utils.BuildState import BuildState
from enkan.utils.Filters import BuildFilters


@dataclass(frozen=True)
class SourceScope:
    """
    Explicit per-source runtime scope used while ingesting/building one input.

    A SourceScope isolates txt-file globals and filter mutations from the shared
    runtime build state and build filters while preserving top-level CLI precedence.
    """

    build_state: BuildState
    build_filters: BuildFilters

    @classmethod
    def from_runtime(
        cls,
        build_state: BuildState,
        build_filters: BuildFilters,
    ) -> "SourceScope":
        return cls(
            build_state=build_state.clone_for_source(),
            build_filters=build_filters.clone_for_source(),
        )
