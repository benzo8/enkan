class TreeNode:
    __slots__ = (
        "name",
        "path",
        "proportion",
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
        name,
        path,
        proportion=None,
        weight_modifier=100,
        is_percentage=True,
        mode_modifier=None,
        flat=False,
        images=None,
        parent=None,
    ):
        self.name = name  # Virtual name of the node
        self.path = path  # Path of the node in the filesystem
        self.proportion = proportion  # Proportion of this node in the tree
        self.weight = None  # Weight for this node
        self.weight_modifier = weight_modifier  # Weight modifier for this node
        self.is_percentage = (
            is_percentage  # Boolean to indicate if the weight is a percentage
        )
        self.mode_modifier = mode_modifier  # Modifier for the mode of this node
        self.flat = flat  # Boolean to indicate if this node is a flat branch
        self.images = images if images else []  # List of images in this node
        self.children = []  # List of child nodes (branches)
        self.parent = parent  # Reference to the parent node

    @property
    def level(self):
        """
        Dynamically compute the level of this node in the tree by traversing up to the root.

        Returns:
            int: The level of this node, with the root node at level 0.
        """
        current = self
        level = 1

        while current.parent:  # Traverse upwards until reaching the root
            level += 1
            current = current.parent

        return level

    @property
    def siblings(self):
        if self.parent:
            return self.parent.children
        return []

    def add_child(self, child_node):
        child_node.parent = self
        self.children.append(child_node)

    def find_node(self, name):
        # Check if the current node is the one we're looking for
        if self.name == name:
            return self

        # Recursively search in the children
        for child in self.children:
            result = child.find_node(name)
            if result:
                return result

        return None  # Node not found

    def get_nodes_at_level(self, target_level):
        nodes_at_level = []

        if self.level == target_level:
            nodes_at_level.append(self)

        for child in self.children:
            nodes_at_level.extend(child.get_nodes_at_level(target_level))

        return nodes_at_level
