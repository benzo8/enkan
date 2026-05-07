from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from enkan.utils.Mode import ModeMap, copy_mode_map, ensure_mode_map


@dataclass
class BuildState:
    """Mutable state used while building and recalculating weighted trees."""

    mode: ModeMap = field(default_factory=lambda: ensure_mode_map(None))
    cli_mode: ModeMap | None = None
    cli_mode_pinned: bool = False
    groups: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config, *, cli_mode_pinned: bool = False) -> "BuildState":
        mode_value = config("slideshow.mode")
        config_mode = ensure_mode_map(mode_value) if mode_value is not None else None
        cli_mode = copy_mode_map(config_mode) if cli_mode_pinned else None
        return cls(
            mode=copy_mode_map(config_mode) or ensure_mode_map(None),
            cli_mode=cli_mode,
            cli_mode_pinned=bool(cli_mode_pinned and cli_mode is not None),
        )

    def clone_for_source(self) -> "BuildState":
        return BuildState(
            mode=copy_mode_map(self.mode) or ensure_mode_map(None),
            cli_mode=copy_mode_map(self.cli_mode),
            cli_mode_pinned=self.cli_mode_pinned,
            groups=copy.deepcopy(self.groups),
        )

    def set_mode(self, mode: Any) -> None:
        self.mode = ensure_mode_map(mode)
