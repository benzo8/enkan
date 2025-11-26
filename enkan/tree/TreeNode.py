from __future__ import annotations
from typing import Any, List, Optional


class TreeNode:
    __slots__ = (
        "name",
        "path",
        "group",
        "proportion",
        "user_proportion",
        "weight",
        "weight_modifier",
        "is_percentage",
        "mode_modifier",
        "flat",
        "images",
        "children",
        "parent",
    )

    def __init__(
        self,
        name: str,
        path: str,
        group: Optional[str] = None,
        proportion: Optional[float] = None,
        user_proportion: Optional[float] = None,
        weight_modifier: int = 100,
        is_percentage: bool = True,
        mode_modifier: Any = None,
        flat: bool = False,
        images: Optional[List[str]] = None,
        parent: Optional["TreeNode"] = None,
    ) -> None:
        self.name: str = name
        self.path: str = path
        self.group: Optional[str] = group
        self.proportion: Optional[float] = proportion
        self.user_proportion: Optional[float] = user_proportion
        self.weight: Optional[float] = None
        self.weight_modifier: int = weight_modifier
        self.is_percentage: bool = is_percentage
        self.mode_modifier: Any = mode_modifier
        self.flat: bool = flat
        self.images: List[str] = list(images) if images else []

        self.children: List["TreeNode"] = []
        self.parent: Optional["TreeNode"] = parent

    @property
    def level(self) -> int:
        """
        Compute depth (root = 1).
        """
        current = self
        level = 1

        while current.parent:  # Traverse upwards until reaching the root
            level += 1
            current: TreeNode = current.parent
        return level

    @property
    def siblings(self) -> List["TreeNode"]:
        return self.parent.children if self.parent else []

    def add_child(self, child_node: "TreeNode") -> None:
        child_node.parent = self
        self.children.append(child_node)

    def find_node(self, name: str) -> Optional["TreeNode"]:
        if self.name == name:
            return self
        for child in self.children:
            found = child.find_node(name)
            if found:
                return found
        return None

    def get_nodes_at_level(self, target_level: int) -> List["TreeNode"]:
        result: List["TreeNode"] = []
        if self.level == target_level:
            result.append(self)
        for child in self.children:
            result.extend(child.get_nodes_at_level(target_level))
        return result
