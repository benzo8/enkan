import os
import random
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import argparse
import re
from collections import defaultdict, deque

# Argument parsing
parser = argparse.ArgumentParser(description='Create a slideshow from a list of files.')
parser.add_argument('--input_file', '-i', metavar='input_file', nargs='?', type=str, help='Input file or Folder to build')
parser.add_argument('--run', dest='run', action='store_true', help='Run the slideshow')
parser.add_argument('--test', metavar='N', type=int, help='Run the test with N iterations')
parser.add_argument('--random', action='store_true', help='Start in Completely Random mode')
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
        self.show_image()
    
    def show_image(self, image_path=None):
        if image_path is None:
            if self.completely_random:
                image_path = random.choice(self.image_paths)
            else:
                image_path = random.choices(self.image_paths, weights=self.weights, k=1)[0]
            self.history.append(image_path)
            self.forward_history.clear()  # Clear forward history when a new image is shown
        self.current_image_path = image_path
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

    def exit_slideshow(self, event=None):
        self.root.destroy()

def count_images_in_directories(directories, ignored_dirs=None, scan_subfolders=True):
    if ignored_dirs is None:
        ignored_dirs = []
    folder_image_paths = defaultdict(list)
    folder_weights = defaultdict(lambda: 0)  # Initialize weights to 0 to accumulate correctly
    for directory in directories:
        weight = 100
        if directory.startswith('[') and ']' in directory:
            weight_str = directory[1:directory.find(']')]
            try:
                weight = int(weight_str)
                directory = directory[directory.find(']') + 1:].strip()
            except ValueError:
                pass
        for root, dirs, files in os.walk(directory):
            if any(ignored in root for ignored in ignored_dirs):
                continue
            images = [os.path.join(root, f) for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))]
            if images:
                folder_image_paths[root].extend(images)
                folder_weights[root] += weight  # Accumulate weights for repeated entries
            if not scan_subfolders:
                break
    # Remove empty folders
    folder_image_paths = {k: v for k, v in folder_image_paths.items() if v}
    folder_weights = {k: v for k, v in folder_weights.items() if k in folder_image_paths}
    return folder_image_paths, folder_weights

def calculate_weights(folder_image_paths, folder_weights, specific_images):
    if not folder_image_paths and not specific_images:
        raise ValueError("No images found in the provided directories and specific images.")
        
    total_folder_weight = sum(folder_weights.values()) / 100
    total_specific_weight = sum(specific_images.values()) / 100
    total_weight = total_folder_weight + total_specific_weight

    if total_weight == 0:
        raise ValueError("Total weight cannot be zero.")

    all_image_paths = []
    weights = []

    # Normalize folder weights
    for folder, images in folder_image_paths.items():
        folder_weight = folder_weights[folder] / 100
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
    for directory, count in sorted(directory_counts.items()):  # Alphabetical order
        print(f"Directory: {directory}, Hits: {count}, Weight: {count / total_images:.2f}")

def parse_input_file(input_file):
    image_dirs = []
    ignored_dirs = []
    specific_images = defaultdict(int)
    with open(input_file, "r", encoding="utf-8") as f:
        content = f.readlines()
        for line in content:
            line = line.replace('"', '').strip()
            if line.startswith("[l]"):
                subfile = line[3:].strip()
                if os.path.isfile(subfile):
                    sub_image_dirs, sub_ignored_dirs, sub_specific_images = parse_input_file(subfile)
                    image_dirs.extend(sub_image_dirs)
                    ignored_dirs.extend(sub_ignored_dirs)
                    for k, v in sub_specific_images.items():
                        specific_images[k] += v  # Accumulate weights for repeated entries
            elif line.startswith("[-]"):
                ignored_dirs.append(line[3:].strip())
            elif os.path.isdir(line):
                image_dirs.append(line)
            else:
                matches = re.match(r'\[(\d+)\](.*)', line)
                if matches:
                    weight = int(matches[1])
                    path = matches[2].strip()
                    if os.path.isdir(path):
                        image_dirs.append(f"[{weight}]{path}")
                    elif os.path.isfile(path):
                        specific_images[path] += weight  # Accumulate weights for repeated entries
                elif os.path.isfile(line):
                    specific_images[line] += 100  # Default weight to 100%
    return image_dirs, ignored_dirs, specific_images

def main(input_files, test_iterations=None, completely_random=False):
    image_dirs = []
    ignored_dirs = []
    specific_images = defaultdict(int)
    for input_filename in input_files:
        if os.path.isfile(input_filename):
            sub_image_dirs, sub_ignored_dirs, sub_specific_images = parse_input_file(input_filename)
            image_dirs.extend(sub_image_dirs)
            ignored_dirs.extend(sub_ignored_dirs)
            for k, v in sub_specific_images.items():
                specific_images[k] += v  # Accumulate weights for repeated entries

    folder_image_paths, folder_weights = count_images_in_directories(image_dirs, ignored_dirs, scan_subfolders=True)
    
    if not folder_image_paths and not specific_images:
        raise ValueError("No images found in the provided directories and specific images.")
        
    all_image_paths, weights = calculate_weights(folder_image_paths, folder_weights, specific_images)
    
    if test_iterations:
        test_distribution(all_image_paths, weights, test_iterations)
    else:
        root = tk.Tk()
        slideshow = ImageSlideshow(root, all_image_paths, weights, completely_random)
        root.mainloop()

if __name__ == "__main__":
    if args.run:
        input_files = args.input_file.split('+') if args.input_file else []
        main(input_files, completely_random=args.random)
    elif args.test:
        input_files = args.input_file.split('+') if args.input_file else []
        main(input_files, test_iterations=args.test, completely_random=args.random)
