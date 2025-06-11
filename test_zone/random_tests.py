import random
from collections import Counter

def generate_cars_and_weights(tree, W):
    """
    Generate a list of cars (images) and their corresponding weights for use with random.choices.
    
    Args:
        tree (dict): Nested dictionary representing the tree structure.
                     Example:
                     {
                         "CarA": {
                             "Blue": 5,  # 5 images in Blue folder of CarA
                             "Red": 10,  # 10 images in Red folder of CarA
                         },
                         "CarB": {
                             "Green": 8,
                             "Yellow": 12,
                         },
                         "CarC": {
                             "Black": 15,
                             "White": 5,
                         },
                     }
        W (float): Total weight to distribute.
    
    Returns:
        cars_list (list): List of all images (e.g., ["A_Blue", "A_Red", "B_Green", ...]).
        weights_list (list): Corresponding list of weights for each image.
    """
    cars_list = []
    weights_list = []

    num_cars = len(tree)  # Number of cars (branches)
    weight_per_car = W / num_cars  # Weight allocated to each car

    for car, colors in tree.items():
        num_colors = len(colors)  # Number of color folders in this car
        weight_per_color = weight_per_car / num_colors  # Weight allocated to each color folder

        for color, num_images in colors.items():
            weight_per_image = weight_per_color / num_images  # Weight allocated to each image

            # Add each image to the list with its corresponding weight
            for _ in range(num_images):
                cars_list.append(f"{car}_{color}")
                weights_list.append(weight_per_image)

    return cars_list, weights_list

# Calculate statistics of the results
# Example usage
tree = {
    "CarA": {"Red": 10},
    "CarB": {"Green": 8, "Yellow": 12},
    "CarC": {"Black": 15, "White": 5, "Silver": 300},
}
W = 100  # Total weight

# Perform a weighted random selection
cars_list, weights_list = generate_cars_and_weights(tree, W)
selections = random.choices(cars_list, weights=weights_list, k=10000)

# Verify the output
print("Cars List:", cars_list[:10])  # Show the first 10 images for brevity
print("Weights List:", weights_list[:10])  # Show the first 10 weights for brevity


stats = Counter(selections)
for car_color, count in stats.items():
    print(f"{car_color}: {count}")