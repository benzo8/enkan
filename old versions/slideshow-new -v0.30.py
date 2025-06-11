import os
import random
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import argparse
import re
from collections import defaultdict, deque

# Argument parsing setup
parser = argparse.ArgumentParser(description='Create a slideshow from a list of files.')
parser.add_argument('--input_file', '-i', metavar='input_file', nargs='?', type=str, help='Input file or Folder to build')
parser.add_argument('--run', dest='run', action='store_true', help='Run the slideshow')
parser.add_argument('--test', metavar='N', type=int, help='Run the test with N iterations')
parser.add_argument('--random', action='store_true', help='Start in Completely Random mode')
parser.add_argument('--total_weight', type=int, default=10000, help='Total weight to be distributed among all images')
args = parser.parse_args()

class ImageSlideshow:
    def __init__(self, root, image_paths, weights, completely_random):
        self.root = root
        self.image_paths = image_paths
        self.weights = weights
        self.original_image_paths = image_paths[:]
        self.original_weights = weights[:]
        self.history = deque(maxlen=10)
        self.forward_history = deque(maxlen=10)
        self.subfolder_mode = False
        self.show_filename = False
        self.completely_random = completely_random
        self.rotation_angle = 0
        
        self.root.configure(background='black')  # Set root background to black
        self.label = tk.Label(root, bg='black')  # Set label background to black
        self.label.pack()
        
        self.filename_label = tk.Label(self.root, bg='black', fg='white', anchor='nw')
        self.mode_label = tk.Label(self.root, bg='black', fg='white', anchor='ne')
        
        self.root.attributes("-fullscreen", True)
        self.root.bind('<space>', self.next_image)
        self.root.bind('<Escape>', self.exit_slideshow)
        self.root.bind('<Left>', self.previous_image)
        self.root.bind('<Right>', self.next_image_forward)
        self.root.bind('<Delete>', self.delete_image)
        self.root.bind('<s>', self.toggle_subfolder_mode)
        self.root.bind('<n>', self.toggle_filename_display)
        self.root.bind('<r>', self.toggle_random_mode)
        self.root.bind('<o>', self.rotate_image)
        self.show_image()
    
    def show_image(self, image_path=None):
        if image_path is None:
            # Choose the next image based on the mode (random or weighted)
            if self.completely_random:
                image_path = random.choice(self.image_paths)
            else:
                image_path = random.choices(self.image_paths, weights=self.weights, k=1)[0]
            self.history.append(image_path)
            self.forward_history.clear()  # Clear forward history when a new image is shown
        self.current_image_path = image_path
        image = Image.open(image_path)
        
        # Apply rotation
        if self.rotation_angle != 0:
            image = image.rotate(self.rotation_angle, expand=True)
        
        # Resize image to fit the screen while maintaining aspect ratio
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
        
        self.update_filename_display()
    
    def next_image(self, event=None):
        self.show_image()
    
    def previous_image(self, event=None):
        if len(self.history) > 1:
            self.forward_history.appendleft(self.history.pop())
            self.show_image(self.history[-1])
    
    def next_image_forward(self, event=None):
        if self.forward_history:
            image_path = self.forward_history.popleft()
            self.history.append(image_path)
            self.show_image(image_path)

    def delete_image(self, event=None):
        if self.current_image_path:
            confirm = messagebox.askyesno("Delete Image", f"Are you sure you want to delete {self.current_image_path}?")
            if confirm:
                try:
                    os.remove(self.current_image_path)
                    index = self.image_paths.index(self.current_image_path)
                    self.image_paths.pop(index)
                    self.weights.pop(index)
                    self.history.pop()  # Remove the current image from history
                    self.show_image()
                except Exception as e:
                    messagebox.showerror("Error", f"Could not delete the image: {e}")

    def toggle_subfolder_mode(self, event=None):
        if not self.subfolder_mode:
            current_dir = os.path.dirname(self.current_image_path)
            self.image_paths = [path for path in self.original_image_paths if path.startswith(current_dir)]
            self.weights = [self.original_weights[i] for i, path in enumerate(self.original_image_paths) if path.startswith(current_dir)]
            self.subfolder_mode = True
        else:
            self.image_paths = self.original_image_paths[:]
            self.weights = self.original_weights[:]
            self.subfolder_mode = False
        self.show_image(self.current_image_path)
        self.update_filename_display()
    
    def toggle_filename_display(self, event=None):
        self.show_filename = not self.show_filename
        self.update_filename_display()
    
    def update_filename_display(self):
        if self.show_filename:
            self.filename_label.config(text=self.current_image_path)
            self.filename_label.place(x=0, y=0)
            
            mode_text = 'R' if self.completely_random else 'W'
            if self.subfolder_mode:
                mode_text = 'S'
            self.mode_label.config(text=mode_text)
            self.mode_label.place(x=self.root.winfo_screenwidth(), y=0, anchor='ne')
        else:
            self.filename_label.place_forget()
            self.mode_label.place_forget()
    
    def toggle_random_mode(self, event=None):
        self.completely_random = not self.completely_random
        self.update_filename_display()
        
    def rotate_image(self, event=None):
        self.rotation_angle = (self.rotation_angle + 90) % 360
        self.show_image(self.current_image_path)

    def exit_slideshow(self, event=None):
        self.root.destroy()

def parse_input_file(input_file):
    image_dirs = defaultdict(lambda: {'weight': 100, 'is_absolute': False})
    specific_images = defaultdict(lambda: {'weight': 100, 'is_absolute': False})
    ignored_dirs = []

    with open(input_file, "r", encoding="utf-8") as f:
        content = f.readlines()
        for line in content:
            line = line.replace('"', '').strip()
            if line.startswith("[l]"):
                subfile = line[3:].strip()
                if os.path.isfile(subfile):
                    sub_image_dirs, sub_specific_images, sub_ignored_dirs = parse_input_file(subfile)
                    image_dirs.update(sub_image_dirs)
                    specific_images.update(sub_specific_images)
                    ignored_dirs.extend(sub_ignored_dirs)
            elif line.startswith("[-]"):
                ignored_dirs.append(line[3:].strip())
            elif os.path.isdir(line):
                image_dirs[line] = {'weight': 100, 'is_absolute': False}
            else:
                matches = re.match(r'\[(\d+)(%?)\](.*)', line)
                if matches:
                    weight = int(matches[1])
                    is_percentage = matches[2] == '%'
                    path = matches[3].strip()
                    if os.path.isdir(path):
                        image_dirs[path] = {'weight': weight, 'is_absolute': not is_percentage}
                    else:
                        specific_images[path] = {'weight': weight, 'is_absolute': not is_percentage}
                elif os.path.isfile(line):
                    specific_images[line] = {'weight': 100, 'is_absolute': False}

    return image_dirs, specific_images, ignored_dirs

def build_folder_lists(directories, ignored_dirs=None, scan_subfolders=True):
    if ignored_dirs is None:
        ignored_dirs = []
    folder_image_paths = defaultdict(lambda: {'weight': 100, 'is_absolute': False})
    folder_data = defaultdict(int)
    
    for path, data in directories.items():
        for root, dirs, files in os.walk(path):
            if any(ignored in dirs for ignored in ignored_dirs):
                continue

            images = [os.path.join(root, f) for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))]
            if images:
                for image in images:
                    folder_image_paths[image] = {'weight': data['weight'], 'is_absolute': data['is_absolute']}
                    folder_data[root] += 1

            # Control whether to scan subfolders by modifying dirs in place
            if not scan_subfolders:
                del dirs[:]  # Clear dirs to prevent descending into subfolders

    # Remove empty folders
    #folder_image_paths = {k: v for k, v in folder_image_paths.items() if v}
    return folder_image_paths, folder_data

def calculate_weights(folder_image_paths, folder_data, specific_images, total_weight=10000):
    if not folder_image_paths and not specific_images:
        raise ValueError("No images found in the provided directories and specific images.")

    all_image_paths = []
    weights = []

    # Calculate the number of folders plus the number of specific images
    num_folders = len(folder_data)
    num_specific_images = len(specific_images)
    total_num_items = num_folders + num_specific_images

    # Calculate weight to be assigned to each folder or specific image
    item_weight = total_weight / total_num_items if total_num_items > 0 else 0

    # Distribute weights for images within each folder
    for path, data in folder_image_paths.items():
        num_images = folder_data[os.path.dirname(path)]
        specific_weight = data['weight']
        is_percentage = not data['is_absolute']
        if is_percentage:
            image_weight = (item_weight / num_images) * (specific_weight / 100)  # Percentage weight per image
        else:
            image_weight = item_weight / specific_weight  # Absolute weight per image
        all_image_paths.append(path)
        weights.append(image_weight)

    # Assign weights to specific images
    for path, data in specific_images.items():
        specific_weight = data['weight']
        is_percentage = not data['is_absolute']
        if is_percentage:
            image_weight = item_weight * (specific_weight / 100)
        else:
            image_weight = item_weight
        all_image_paths.append(path)
        weights.append(image_weight)

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
    for directory, count in sorted(directory_counts.items()):  # Alphabetical order
        print(f"Directory: {directory}, Hits: {count}, Weight: {count / total_images:.2f}")

def main(input_files, test_iterations=None, completely_random=False, total_weight=10000):
    image_dirs = defaultdict(lambda: {'weight': 100, 'is_absolute': False})
    specific_images = defaultdict(lambda: {'weight': 100, 'is_absolute': False})
    ignored_dirs = []

    for input_filename in input_files:
        if os.path.isfile(input_filename):
            sub_image_dirs, sub_specific_images, sub_ignored_dirs = parse_input_file(input_filename)
            image_dirs.update(sub_image_dirs)
            specific_images.update(sub_specific_images)
            ignored_dirs.extend(sub_ignored_dirs)

    folder_image_paths, folder_data = build_folder_lists(image_dirs, ignored_dirs, scan_subfolders=True)

    if not folder_image_paths and not specific_images:
        raise ValueError("No images found in the provided directories and specific images.")

    all_image_paths, weights = calculate_weights(folder_image_paths, folder_data, specific_images, total_weight)

    if test_iterations:
        test_distribution(all_image_paths, weights, test_iterations)
    else:
        root = tk.Tk()
        slideshow = ImageSlideshow(root, all_image_paths, weights, completely_random)
        root.mainloop()

if __name__ == "__main__":
    if args.run:
        input_files = args.input_file.split('+') if args.input_file else []
        main(input_files, completely_random=args.random, total_weight=args.total_weight)
    elif args.test:
        input_files = args.input_file.split('+') if args.input_file else []
        main(input_files, test_iterations=args.test, completely_random=args.random, total_weight=args.total_weight)
