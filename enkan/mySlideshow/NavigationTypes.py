from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NavigationBasis(str, Enum):
    FOLDER = "folder"
    BRANCH = "branch"


class ScopeKind(str, Enum):
    ROOT = "root"
    PARENT = "parent"
    SUBFOLDER = "subfolder"


@dataclass(frozen=True)
class NavigationState:
    basis: NavigationBasis
    scope_kind: ScopeKind
    branch_anchor: str | None = None

    @property
    def is_branch(self) -> bool:
        return self.basis is NavigationBasis.BRANCH

    @property
    def is_folder(self) -> bool:
        return self.basis is NavigationBasis.FOLDER

    @property
    def is_root(self) -> bool:
        return self.scope_kind is ScopeKind.ROOT

    @property
    def is_parent(self) -> bool:
        return self.scope_kind is ScopeKind.PARENT

    @property
    def is_subfolder(self) -> bool:
        return self.scope_kind is ScopeKind.SUBFOLDER
