import numpy as np
import matplotlib.pyplot as plt

def calculate_weights(node, mode_map, total_weight=100, level=1, inherited_mode="b"):
    """ Recursively calculate weights for a given folder node based on the mode map, supporting weighted slopes """
    
    children = node.get("children", [])  # Subfolders or images
    images = node.get("images", [])  # Images directly inside this node
    
    # Determine the mode for the current level (inherit if not explicitly stated)
    current_mode = mode_map.get(level, inherited_mode)
    
    # Extract slope (if defined, e.g., "w2,5%")
    slope_modifier = 0
    if isinstance(current_mode, tuple):  # If mode is a tuple (w, slope)
        current_mode, slope_modifier = current_mode

    if not children and images:
        # Leaf node (image folder): distribute weight to images
        if current_mode == "b":  # Balanced at image level
            weight_per_image = total_weight / len(images)
            return {img: weight_per_image for img in images}
        elif current_mode == "w":  # Weighted at image level
            return {img: total_weight / len(images) for img in images}  # Equal weight per image
    
    # Non-leaf node (folder) weight distribution
    num_children = len(children)
    child_weights = {}

    if current_mode == "b":  # Balanced at this level
        weight_per_child = total_weight / num_children
        child_weights = {child["name"]: weight_per_child for child in children}
    
    elif current_mode == "w":  # Weighted at this level, possibly with a slope
        # Sort children by image count
        sorted_children = sorted(children, key=lambda x: x["num_images"])
        image_counts = np.array([child["num_images"] for child in sorted_children])
        
        if slope_modifier > 0:
            # Compute slope adjustment
            min_weight_adj = (1 + slope_modifier / 100)
            max_weight_adj = (1 - slope_modifier / 100)
            adjustments = np.linspace(min_weight_adj, max_weight_adj, len(sorted_children))
            adjusted_weights = image_counts * adjustments
        else:
            adjusted_weights = image_counts  # No slope modifier
        
        # Normalize adjusted weights to keep total_weight consistent
        total_adjusted = sum(adjusted_weights)
        for child, adj_weight in zip(sorted_children, adjusted_weights):
            child_weights[child["name"]] = (adj_weight / total_adjusted) * total_weight
    
    # Recurse with mode inheritance
    result = {}
    for child in children:
        result.update(calculate_weights(child, mode_map, child_weights[child["name"]], level + 1, current_mode))
    
    return result

# Sample folder structure
sample_tree = {
    "name": "Cars",
    "children": [
        {"name": "Ford", "num_images": 100, "children": []},
        {"name": "Toyota", "num_images": 50, "children": []},
        {"name": "BMW", "num_images": 200, "children": []},
    ]
}

# Test mode configuration
# Balanced at level 1, Weighted with 5% bias at level 2
mode_config = {
    2: ("w", 5)  # Weighted at level 2 with a 5% bias applied
}

# Compute weights
weights = calculate_weights(sample_tree, mode_config)

# Display results
print("Computed Weights:")
for key, value in weights.items():
    print(f"{key}: {value:.2f}")

# Visualization
names = list(weights.keys())
values = list(weights.values())

plt.figure(figsize=(10, 5))
plt.bar(names, values)
plt.xlabel("Car Brand")
plt.ylabel("Weight Percentage")
plt.title("Image Selection Probability Distribution")
plt.show()
