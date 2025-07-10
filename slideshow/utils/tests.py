import os
import random
from collections import defaultdict
from tqdm import tqdm

from slideshow.constants import TOTAL_WEIGHT

def test_distribution(image_nodes, weights, iterations, testdepth, defaults, quiet=False):
    hit_counts = defaultdict(int)
    for _ in tqdm(range(iterations), desc="Iterating tests", disable=quiet):
        if defaults.is_random:
            image_path = random.choice(image_nodes)
        else:
            image_path = random.choices(image_nodes, weights=weights, k=1)[0]
        hit_counts["\\".join(image_path.split("\\")[:testdepth])] += 1

    directory_counts = defaultdict(int)
    for path, count in hit_counts.items():
        if os.path.isfile(path):
            directory = os.path.dirname(path)
        else:
            directory = path
        directory_counts[directory] += count

    total_images = len(image_nodes)
    for directory, count in sorted(directory_counts.items()):  # Alphabetical order
        print(
            f"Directory: {directory}, Hits: {count}, %age: {count / iterations * 100:.2f}%, Weight: {count / total_images * TOTAL_WEIGHT:.2f}"
        )