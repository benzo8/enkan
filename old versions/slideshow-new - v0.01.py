import os
import random
import tkinter as tk
from PIL import Image, ImageTk
import argparse
import re
from collections import defaultdict

# Argument parsing
parser = argparse.ArgumentParser(description='Create a slideshow from a list of files.')
parser.add_argument('--input_file', '-i', metavar='input_file', nargs='?', type=str, help='Input file or Folder to build')
parser.add_argument('--run', dest='run', action='store_true', help='Run the slideshow')
parser.add_argument('--test', metavar='N', type=int, help='Run the test with N iterations')
args = parser.parse_args()

class ImageSlideshow:
    def __init__(self, root, image_paths, weights):
        self.root = root
        self.image_paths = image_paths
        self.weights = weights
        
        self.root.configure(background='black')  # Set root background to black
        self.label = tk.Label(root, bg='black')  # Set label background to black
        self.label.pack()
        
        self.root.attributes("-fullscreen", True)
        self.root.bind('<space>', self.next_image)
        self.root.bind('<Escape>', self.exit_slideshow)
        self.show_image()
    
    def show_image(self):
        image_path = random.choices(self.image_paths, weights=self.weights, k=1)[0]
        image = Image.open(image_path)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        image_ratio = image.width / image.height
        screen_ratio = screen_width / screen_height
        
        if image_ratio > screen_ratio:
            new_width = screen_width
            new_height = int(screen_width / image_ratio)
        else:
            new_height = screen_height
            new_width = int(screen_height * image_ratio)
        
        image = image.resize((new_width, new_height), Image.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        self.label.config(image=photo)
        self.label.image = photo
    
    def next_image(self, event=None):
        self.show_image()

    def exit_slideshow(self, event=None):
        self.root.destroy()

def count_images_in_directories(directories, ignored_dirs=None, scan_subfolders=True):
    if ignored_dirs is None:
        ignored_dirs = []
    folder_image_paths = defaultdict(list)
    for directory in directories:
        for root, dirs, files in os.walk(directory):
            if any(ignored in root for ignored in ignored_dirs):
                continue
            images = [os.path.join(root, f) for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))]
            if images:
                folder_image_paths[root].extend(images)
            if not scan_subfolders:
                break
    return folder_image_paths

def calculate_weights(folder_image_paths, specific_images):
    num_folders = len(folder_image_paths)
    all_image_paths = []
    weights = []

    if num_folders == 0 and not specific_images:
        raise ValueError("No folders or specific images to process.")

    # Each folder gets a weight of 1
    folder_weight = 1
    total_folder_weight = num_folders * folder_weight
    total_specific_weight = sum(specific_images.values()) / 100
    total_weight = total_folder_weight + total_specific_weight

    if total_weight == 0:
        raise ValueError("Total weight cannot be zero.")

    # Normalize folder weights
    for images in folder_image_paths.values():
        image_weight = folder_weight / len(images) / total_weight
        for image in images:
            all_image_paths.append(image)
            weights.append(image_weight)

    # Normalize specific image weights
    for path, percentage in specific_images.items():
        specific_weight = (percentage / 100) / total_weight
        all_image_paths.append(path)
        weights.append(specific_weight)

    return all_image_paths, weights

def test_distribution(image_paths, weights, iterations):
    hit_counts = defaultdict(int)
    for _ in range(iterations):
        image_path = random.choices(image_paths, weights=weights, k=1)[0]
        hit_counts[image_path] += 1

    directory_counts = defaultdict(int)
    for path, count in hit_counts.items():
        directory = os.path.dirname(path)
        directory_counts[directory] += count

    total_images = len(image_paths)
    for directory, count in directory_counts.items():
        print(f"Directory: {directory}, Hits: {count}, Weight: {count / total_images:.2f}")

def main(input_files, test_iterations=None):
    image_dirs = []
    ignored_dirs = []
    specific_images = {}
    for input_filename in input_files:
        if os.path.isfile(input_filename):
            with open(input_filename, "r", encoding="utf-8") as f:
                content = f.readlines()
                for line in content:
                    line = line.replace('"', '').strip()
                    if line.startswith("[l]"):
                        subfile = line[3:].strip()
                        if os.path.isfile(subfile):
                            with open(subfile, "r", encoding="utf-8") as sf:
                                subfile_content = sf.readlines()
                                for subfile_line in subfile_content:
                                    subfile_line = subfile_line.replace('"', '').strip()
                                    if os.path.isdir(subfile_line):
                                        image_dirs.append(subfile_line)
                    elif line.startswith("[-]"):
                        ignored_dirs.append(line[3:].strip())
                    elif os.path.isdir(line):
                        image_dirs.append(line)
                    else:
                        matches = re.match(r'\[(\d+)\](.*)', line)
                        if matches:
                            weight = int(matches[1])
                            image_path = matches[2].strip()
                            if os.path.isfile(image_path):
                                specific_images[image_path] = weight
                        elif os.path.isfile(line):
                            specific_images[line] = 100  # Default weight to 100%

    folder_image_paths = count_images_in_directories(image_dirs, ignored_dirs, scan_subfolders=True)
    all_image_paths, weights = calculate_weights(folder_image_paths, specific_images)
    
    if test_iterations:
        test_distribution(all_image_paths, weights, test_iterations)
    else:
        root = tk.Tk()
        slideshow = ImageSlideshow(root, all_image_paths, weights)
        root.mainloop()

if __name__ == "__main__":
    if args.run:
        input_files = args.input_file.split('+') if args.input_file else []
        main(input_files)
    elif args.test:
        input_files = args.input_file.split('+') if args.input_file else []
        main(input_files, test_iterations=args.test)
