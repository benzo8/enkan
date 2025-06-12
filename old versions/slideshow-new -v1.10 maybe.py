import argparse
import os
import random
import re
# import sys
import tkinter as tk
from collections import defaultdict, deque
from tkinter import messagebox
from tqdm import tqdm

from PIL import Image, ImageTk

# Constants
TOTAL_WEIGHT = 100
PARENT_STACK_MAX = 5
QUEUE_LENGTH_MAX = 10
IMAGE_FILES = (".png", ".jpg", ".jpeg", ".gif", ".bmp")
TEXT_FILES = (".txt")
              
# Argument parsing setup
class ModeAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if len(values) == 1:
            if values[0] not in ["weighted", "balanced", "flat", "plain"]:
                parser.error(
                    f"Invalid choice: '{values[0]}'. Choose from 'weighted', 'balanced', 'flat', 'plain'."
                )
            setattr(namespace, self.dest, (values[0], 0))
        elif len(values) == 2:
            if values[0] not in ["weighted", "balanced"]:
                parser.error(
                    f"Invalid choice: '{values[0]}'. Choose from 'weighted', 'balanced'."
                )
            try:
                level = int(values[1])
            except ValueError:
                parser.error(f"Invalid level: '{values[1]}'. Must be an integer.")
            setattr(namespace, self.dest, (values[0], level))

parser = argparse.ArgumentParser(description="Create a slideshow from a list of files.")
parser.add_argument(
    "--input_file",
    "-i",
    metavar="input_file",
    nargs="+",
    type=str,
    help="Input file or Folder to build",
)
parser.add_argument("--run", dest="run", action="store_true", help="Run the slideshow")
parser.add_argument(
    "--mode",
    nargs="+",
    action=ModeAction,
    help="Set the mode: (weighted) or (balanced [x])",
)
parser.add_argument(
    "--depth",
    type=int,
    help="Depth below which to combine all folders into one",
)
parser.add_argument(
    "--random", action="store_true", help="Start in Completely Random mode"
)
parser.add_argument(
    "--test", metavar="N", type=int, help="Run the test with N iterations"
)
parser.add_argument(
    "--testdepth", type=int, default=None, help="Depth to display test results"
)
parser.add_argument(
    "--printtree", action="store_true", help="Print the tree structure"
)
args = parser.parse_args()

class ImageSlideshow:
    def __init__(self, root, image_paths, weights, tree, defaults):
        self.root = root
        self.image_paths = image_paths
        self.weights = weights
        self.tree = tree
        self.original_image_paths = image_paths
        self.number_of_images = len(image_paths)
        self.current_image_index = 0
        self.original_weights = weights
        self.subFolderStack = Stack(1)
        self.parentFolderStack = Stack(PARENT_STACK_MAX)
        self.history = deque(maxlen=QUEUE_LENGTH_MAX)
        self.forward_history = deque(maxlen=QUEUE_LENGTH_MAX)
        self.subfolder_mode = False
        self.parent_mode = False
        self.show_filename = False

        self.screen_width = root.winfo_screenwidth()
        self.screen_height = root.winfo_screenheight()

        self.initial_mode = defaults.mode
        if defaults.is_random:
            self.mode, self.mode_level = ("random", defaults.mode[1])
        else:
            self.mode, self.mode_level = defaults.mode

        self.rotation_angle = 0

        self.root.configure(background="black")  # Set root background to black
        self.label = tk.Label(root, bg="black")  # Set label background to black
        self.label.pack()

        # self.filename_label = tk.Label(self.root, bg="black", fg="white", anchor="nw")
        
        self.filename_label = tk.Text(self.root, bg='black', fg='white', height=1, wrap='none', bd=0, highlightthickness=0)
        self.filename_label.config(state=tk.DISABLED)
        self.mode_label = tk.Label(self.root, bg="black", fg="white", anchor="ne")

        self.root.attributes("-fullscreen", True)
        self.root.bind("<space>", self.next_image)
        self.root.bind("<Escape>", self.exit_slideshow)
        self.root.bind("<Left>", self.previous_image)
        self.root.bind("<Right>", self.next_image_forward)
        self.root.bind("<Delete>", self.delete_image)
        self.root.bind("<s>", self.toggle_subfolder_mode)
        self.root.bind("<p>", self.follow_branch_down)
        self.root.bind("<o>", self.follow_branch_up)
        self.root.bind("<i>", self.step_backwards)
        self.root.bind("<u>", self.reset_parent_mode)
        self.root.bind("<n>", self.toggle_filename_display)
        self.root.bind("<c>", self.toggle_random_mode)
        self.root.bind("<r>", self.rotate_image)
        self.show_image()

    def show_image(self, image_path=None):
        if image_path is None:
            # Choose the next image based on the mode (random or weighted)
            if self.mode == "random":
                image_path = random.choice(self.image_paths)
            else:
                image_path = random.choices(
                    self.image_paths, weights=self.weights, k=1
                )[0]
            self.history.append(image_path)
            self.forward_history.clear()  # Clear forward history when a new image is shown
        self.current_image_path = image_path
        self.current_image_index = self.image_paths.index(image_path)
        image = Image.open(image_path)

        # Apply rotation
        if self.rotation_angle != 0:
            image = image.rotate(self.rotation_angle, expand=True)

        # Resize image to fit the screen while maintaining aspect ratio
        screen_width = self.screen_width
        screen_height = self.screen_height
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
        if self.rotation_angle != 0:
            self.rotation_angle = 0
        self.show_image()

    def previous_image(self, event=None):
        if len(self.history) > 1:
            self.forward_history.appendleft(self.history.pop())
            if self.rotation_angle != 0:
                self.rotation_angle = 0
            self.show_image(self.history[-1])

    def next_image_forward(self, event=None):
        if self.forward_history:
            image_path = self.forward_history.popleft()
            self.history.append(image_path)
            if self.rotation_angle != 0:
                self.rotation_angle = 0
            self.show_image(image_path)

    def delete_image(self, event=None):
        if self.current_image_path:
            confirm = messagebox.askyesno(
                "Delete Image",
                f"Are you sure you want to delete {self.current_image_path}?",
            )
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

    def subfolder_mode_on(self):
        current_dir = os.path.dirname(self.current_image_path)

        self.subFolderStack.push(current_dir, self.image_paths, self.weights)

        temp_image_paths = [
            path for path in self.image_paths if path.startswith(current_dir)
        ]
        temp_weights = [
            self.weights[i]
            for i, path in enumerate(self.image_paths)
            if path.startswith(current_dir)
        ]

        self.image_paths = temp_image_paths
        self.weights = temp_weights

        self.number_of_images = len(
            self.image_paths
        )  # Update the number of images for the subfolder
        self.current_image_index = self.image_paths.index(
            self.current_image_path
        )
        self.subfolder_mode = True
    
    def subfolder_mode_off(self):
        current_dir, self.image_paths, self.weights = self.subFolderStack.pop()
        self.number_of_images = len(
            self.image_paths
        )  # Update the number of images for the full set
        self.current_image_index = self.image_paths.index(
            self.current_image_path
        )  # Update to the current image index
        self.subfolder_mode = False

    def toggle_subfolder_mode(self, event=None):
        if not self.subfolder_mode:
            self.subfolder_mode_on()
        else:
            self.subfolder_mode_off()
        self.show_image(self.current_image_path)
        self.update_filename_display()

    """ TODO:
            Fix follow_branch_down and follow_branch_up
    """
    
    def follow_branch_down(self, event=None):
        """Move down one level in the folder structure, build a new tree, and update the slideshow."""
        # Check if the stack is full (S0)
        if self.parentFolderStack.is_full():
            print("S0 - Doing nothing")
            return

        # Turn off subfolder mode if in parent mode (S4)
        if self.subfolder_mode and self.parent_mode:
            self.subfolder_mode_off()
            self.show_image(self.current_image_path)
            self.update_filename_display()
            return

        # Handle navigating up the folder structure (S2)
        if not self.parent_mode:
            current_path = os.path.dirname(self.current_image_path)
            current_path_level = level_of(current_path)

            # Traverse up levels until a valid parent is found
            for i in range(current_path_level - 1, 1, -1):
                parent_level = i
                parent_path = truncate_path(current_path, parent_level)
                if contains_subdirectory(parent_path) > 1 or contains_files(parent_path):
                    break

            self.parentFolderStack.push(
                parent_path, self.original_image_paths, self.original_weights
            )
        else:  # Handle moving up a level in parent mode (S3)
            previous_path = self.parentFolderStack.read_top()
            parent_level = level_of(previous_path) - 1
            parent_path = truncate_path(previous_path, parent_level)

            # If we're backtracking, step backwards instead
            if parent_path == self.parentFolderStack.read_top(2):
                self.step_backwards()
                return

            self.parentFolderStack.push(parent_path, self.image_paths, self.weights)

        # Check if the parent path exists and is a directory
        if os.path.isdir(parent_path):
            # Prepare for building the new tree
            self.image_paths = []
            self.weights = []

            parent_tree = Tree()  # Use newTree instead of Tree
            parent_image_dirs = {
                parent_path: {
                    "weight_modifier": 100,
                    "is_percentage": True,
                    "proportion": None,
                    "depth": defaults.depth,
                }
            }

            # Build the new tree and extract images and weights
            parent_tree.build_tree(parent_image_dirs, None, defaults)
            parent_tree.calculate_branch_weights(mode=defaults.mode[0], balance_level=1)
            self.image_paths, self.weights = parent_tree.extract_image_paths_and_weights_from_tree()

            # Update slideshow state
            self.number_of_images = len(self.image_paths)
            self.current_image_index = 0
            self.parent_mode = True
            self.subfolder_mode = False
            self.subFolderStack.clear()

            self.show_image(self.current_image_path)
            self.update_filename_display()
        else:
            print("No parent branch found.")

    def follow_branch_up(self, event=None):
        """Move up one level in the tree and update the slideshow."""
        if self.parentFolderStack.is_full() or not self.parent_mode: # Test for S0 or trying to move up when not in parent_mode                  
            print("S0 - Doing nothing")
            return 
            
        if self.subfolder_mode and not self.parentFolderStack.is_empty(): # S4
            self.subfolder_mode_off()
            self.show_image(self.current_image_path)
            self.update_filename_display()
            return
        
        # if not self.parent_mode: # S2
        current_path = os.path.dirname(self.current_image_path)
        current_top = self.parentFolderStack.read_top()
        if contains_subdirectory(current_top):
            current_path_level = level_of(current_top)            
            parent_level = current_path_level + 1
            parent_path = truncate_path(current_path, parent_level)
            
            if parent_path == self.parentFolderStack.read_top(2):
                self.step_backwards()
                return
            
            self.parentFolderStack.push(
                parent_path, self.original_image_paths, self.original_weights
            )
            # else: # S3
            #     previous_path = self.parentFolderStack.read_top()
            #     parent_level = level_of(previous_path) + 1
            #     parent_path = truncate_path(previous_path, parent_level)
            #     self.parentFolderStack.push(parent_path, self.image_paths, self.weights)

            if os.path.isdir(parent_path):

                parent_image_dirs = {}
                self.image_paths = []
                self.weights = []

                parent_tree = Tree(defaults.mode[1])
                parent_image_dirs[parent_path] = {
                    "weight_modifier": 100,
                    "is_percentage": True,
                    "proportion": None,
                    "balance_level": defaults.mode[1],
                    "depth": defaults.depth,
                }
                parent_tree.build_tree(parent_image_dirs, None, defaults)
                self.image_paths, self.weights = (
                    parent_tree.extract_image_paths_and_weights_from_tree()
                )
                self.number_of_images = len(
                    self.image_paths
                )  # Update the number of images for the subfolder
                self.current_image_index = (
                    0  # Reset the current image index for the subfolder
                )
                self.parent_mode = True
                self.subfolder_mode = False
                self.subFolderStack.clear()

                self.show_image(self.current_image_path)
                self.update_filename_display()
        else:
            print("No parent branch found.")

    def step_backwards(self, event=None):
        """Move back in the history and update the slideshow."""
        current_path, self.image_paths, self.weights = self.parentFolderStack.pop()
        self.number_of_images = len(
            self.image_paths
        )  # Update the number of images for the full set
        try:
            self.current_image_index = self.image_paths.index(
                self.current_image_path
            )  # Update to the current image index
        except ValueError:
            self.current_image_index = random.randint(0, self.number_of_images - 1)
            self.current_image_path = self.image_paths[self.current_image_index]
        if self.parentFolderStack.is_empty():
            self.parent_mode = False
        self.subfolder_mode = False

        self.show_image(self.current_image_path)
        self.update_filename_display()
            
    def reset_parent_mode(self, event=None):
        if self.parent_mode:
            self.image_paths, self.weights = self.original_image_paths, self.original_weights
            self.number_of_images = len(
                self.image_paths
            )  # Update the number of images for the full set
            try:
                self.current_image_index = self.image_paths.index(
                    self.current_image_path
                )  # Update to the current image index
            except ValueError:
                self.current_image_index = random.randint(0, self.number_of_images - 1)
                self.current_image_path = self.image_paths[self.current_image_index]
            self.parentFolderStack.clear()
            self.parent_mode = False
            self.subfolder_mode = False
            
            self.show_image(self.current_image_path)
            self.update_filename_display()

    def toggle_filename_display(self, event=None):
        self.show_filename = not self.show_filename
        self.update_filename_display()

    def update_filename_display(self):
        if self.show_filename:
            fixed_colour = None
            self.filename_label.config(state=tk.NORMAL)
            # Clear the previous text
            self.filename_label.delete("1.0", tk.END)

            # Determine the filename display text and color scheme
            if self.subfolder_mode:
                fixed_path = self.subFolderStack.read_top()
                fixed_colour = 'tomato'      
            elif self.parent_mode:
                fixed_path = self.parentFolderStack.read_top()  # The "fixed" portion of the path
                fixed_colour = 'gold'      
            if fixed_colour:
                if self.current_image_path.startswith(fixed_path):
                    fixed_portion = fixed_path
                    remaining_portion = self.current_image_path[len(fixed_path):]
                else:
                    fixed_portion = ""
                    remaining_portion = self.current_image_path

                self.filename_label.insert(tk.END, fixed_portion, "fixed")
                self.filename_label.insert(tk.END, remaining_portion, "normal")
            else:
                # In normal mode, the entire filename is in white
                self.filename_label.insert(tk.END, self.current_image_path, "normal")
                fixed_colour = 'white'

            # Apply the tags for coloring
            self.filename_label.tag_configure("fixed", foreground=fixed_colour)
            self.filename_label.tag_configure("normal", foreground="white")

            # Set the filename label position
            self.filename_label.place(x=0, y=0)
            self.filename_label.config(height=1, width=len(self.current_image_path) + 10, bg='black')

            # Disable the text widget to prevent editing
            self.filename_label.config(state=tk.DISABLED)
            
            # filename_text = f"{self.current_image_path}"
            # self.filename_label.config(text=filename_text)
            # self.filename_label.place(x=0, y=0)

            if self.mode == "random":
                mode_text = "R"
            else:
                mode_text = "W" if self.mode == "weighted" else "B"
            if self.subfolder_mode:
                mode_text += " S"
                subfolder_number_of_images = len(
                    self.image_paths
                )  # Number of images in the subfolder
                subfolder_current_image_index = (
                    self.image_paths.index(self.current_image_path) + 1
                )  # Current index in the subfolder
                mode_text = f"({subfolder_current_image_index}/{subfolder_number_of_images}) {mode_text}"
            elif self.parent_mode:
                mode_text += " P" + str(self.parentFolderStack.len())
                # mode_text = "(" + str(self.parentFolderStack.read_top()) +") " + mode_text + " P" + str(self.parentFolderStack.len())
                parent_number_of_images = len(
                    self.image_paths
                )  # Number of images in the subfolder
                parent_current_image_index = (
                    self.image_paths.index(self.current_image_path) + 1
                )  # Current index in the subfolder
                mode_text = f"({parent_current_image_index}/{parent_number_of_images}) {mode_text}"
            else:
                mode_text = f"({self.current_image_index + 1}/{self.number_of_images}) {mode_text}"

            self.mode_label.config(text=mode_text)
            self.mode_label.place(x=self.root.winfo_screenwidth(), y=0, anchor="ne")
        else:
            self.filename_label.place_forget()
            self.mode_label.place_forget()

    def toggle_random_mode(self, event=None):
        if self.mode == "random":
            self.mode = self.initial_mode
        else:
            self.mode = "random"
        self.update_filename_display()

    def rotate_image(self, event=None):
        self.rotation_angle = (self.rotation_angle - 90) % 360
        self.show_image(self.current_image_path)

    def exit_slideshow(self, event=None):
        self.root.destroy()

class TreeNode:
    def __init__(self, name, path, proportion=None, weight_modifier=100, is_percentage=True, flat=False, images=None, parent=None):
        self.name = name                                # Virtual name of the node
        self.path = path                                # Path of the node in the filesystem
        self.proportion = proportion                    # Proportion of this node in the tree
        self.weight = None                              # Weight for this node
        self.weight_modifier = weight_modifier          # Weight modifier for this node
        self.is_percentage = is_percentage              # Boolean to indicate if the weight is a percentage
        self.images = images if images else []          # List of images in this node
        self.children = []                              # List of child nodes (branches)
        self.parent = parent                            # Reference to the parent node

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

class Tree:
    def __init__(self):
        self.root = TreeNode("root", 0)
        self.node_lookup = {"root": self.root}

    def build_tree(self, image_dirs, specific_images, defaults):
        """
        Read image_dirs and specific_images and build a tree.
        """
        # Initialize tqdm progress bar
        with tqdm(total=0, desc="Building tree", unit="file") as pbar:
            for root, data in image_dirs.items():
                if data.get("flat", False):
                    self.add_flat_branch(root, data)
                else:
                    # Process each directory
                    self.process_directory(root, data, defaults, pbar)
                
                self.handle_grafting(root, data.get("graft_level"), data.get("group"))
                    

        # Handle specific images if provided
        if specific_images:
            self.process_specific_images(specific_images, defaults)

    def process_directory(self, root, data, defaults, pbar):
        """
        Process a single root directory and add nodes to the tree.
        Handles image processing and grafting.
        """
        root_level = level_of(root)
        depth = data.get("depth", defaults.depth)

        # Traverse the directory tree
        for path, dirs, files in os.walk(root):
            if filters.passes(path) == 0:
                # Update the total for new files discovered
                pbar.total += len(files)
                pbar.refresh()
                self.process_path(path, files, dirs, data, root_level, depth, pbar)
            elif filters.passes(path) == 1:
                del dirs[:]  # Prune directories

    def preprocess_ignored_files(self, ignored_files):
        """
        Preprocess ignored_dirs to extract directory paths.

        Args:
            ignored_dirs (list): List of ignored file paths.

        Returns:
            set: Set of directory paths containing ignored files.
        """
        ignored_files_dirs = set()
        for ignored in ignored_files:
            dir_path = os.path.dirname(ignored)  # Get the directory path
            ignored_files_dirs.add(dir_path)
        return ignored_files_dirs

    def process_files(self, path, files, filters):
        """
        Process files in the current directory, ignoring specified files.

        Args:
            path (str): Current directory path.
            files (list): List of files in the current directory.
            filters (object): Object containing ignored_dirs.

        Returns:
            list: List of valid image file paths.
        """
        # Preprocess ignored_dirs once (outside this function)
        if not hasattr(filters, "ignored_dirs_set"):
            filters.ignored_files_dirs = self.preprocess_ignored_files(filters.ignored_files)

        # Check if the current directory is in ignored_dirs_set
        if path in filters.ignored_files_dirs:
            # Filter out ignored files from the current directory
            valid_files = [
                f for f in files
                if os.path.join(path, f) not in filters.ignored_files
            ]
        else:
            # No ignored files in this directory
            valid_files = files

        # Filter for valid image files
        images = [
            os.path.join(path, f)
            for f in valid_files
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp"))
        ]

        return images

    def process_path(self, path, files, dirs, data, root_level, depth, pbar):
        """
        Process an individual path, adding images or virtual nodes as needed.
        """
        images = self.process_files(path, files, filters)
        
        if not images:
            return

        # Dynamically update the progress bar as files are processed
        for _ in images:
            # Simulate processing the file
            pbar.update(1)

        path_level = self.calculate_level(path)
        path_depth = path_level - root_level

        if dirs:
            # Create a special "images" branch for directories with images
            self.add_images_branch(path, images, path_level + 1, depth, data)
        elif path_depth > depth:
            # Truncate to a virtual path
            self.add_virtual_branch(path, images, root_level, depth, data)
        else:
            # Add a regular branch
            self.add_regular_branch(path, images, path_level, depth, data)

    def flatten_branch(self, root):
        """
        Collect all images from the branch rooted at `root`, including subdirectories.

        Args:
            root (str): The root directory of the branch.

        Returns:
            list: A list of full paths to all images in the branch.
        """
        images = []
        for path, _, files in os.walk(root):
            images.extend(
                os.path.join(path, f)
                for f in files
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp"))
            )
        return images

    def add_flat_branch(self, path, data):
        """
        Add a special 'flat' branch for directories with images.
        """
        
        def flatten_branch(self, root):
            """
            Collect all images from the branch rooted at `root`, including subdirectories.

            Args:
                root (str): The root directory of the branch.

            Returns:
                list: A list of full paths to all images in the branch.
            """
            images = []
            for path, _, files in os.walk(root):
                images.extend(
                    os.path.join(path, f)
                    for f in files
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp"))
                )
            return images
        
        images = self.flatten_branch(path)
        level = data.get("level", self.calculate_level(path))
        depth = data.get("depth", 9999)
        
        self.append_overwrite_or_update(
            path,
            level,
            depth,
            {
                "weight_modifier": data.get("weight_modifier", 100),
                "is_percentage": data.get("is_percentage", True),
                "proportion": data.get("proportion", None),
                "images": images,
            },
        )

    def add_images_branch(self, path, images, level, depth, data):
        """
        Add a special 'images' branch for directories with images.
        """
        images_path = os.path.join(path, "images")
        self.append_overwrite_or_update(
            images_path,
            level,
            depth,
            {
                "weight_modifier": 100,
                "is_percentage": True,
                "proportion": data.get("proportion", None),
                "images": images,
            },
        )

    def add_virtual_branch(self, path, images, root_level, depth, data):
        """
        Add a virtual branch when the path depth exceeds the allowed depth.
        """
        virtual_path_level = root_level + depth
        virtual_path = os.path.join(
            *path.split(os.path.sep)[:virtual_path_level - 1], "Virtual"
        )
        self.append_overwrite_or_update(
            virtual_path,
            virtual_path_level,
            depth,
            {
                "weight_modifier": data.get("weight_modifier", 100),
                "is_percentage": data.get("is_percentage", True),
                "proportion": data.get("proportion", None),
                "images": images,
            },
        )

    def add_regular_branch(self, path, images, level, depth, data):
        """
        Add a regular branch for paths that don't need truncation.
        """
        self.append_overwrite_or_update(
            path,
            level,
            depth,
            {
                "weight_modifier": data.get("weight_modifier", 100),
                "is_percentage": data.get("is_percentage", True),
                "proportion" : data.get("proportion", None),
                "images": images,
            },
        )

    def handle_grafting(self, root, graft_level, group):
        if not graft_level and not group:
            return
        """
        Handle grafting by adjusting the tree structure after the directory is processed.
        """
        current_node_name = self.convert_path_to_tree_format(root)
        current_node = self.find_node(current_node_name)
        current_node_parent = current_node.parent

        if not current_node:
            print(f"Warning: Node '{current_node_name}' not found for grafting. Skipping.")
            return

        levelled_name = self.convert_path_to_tree_format(self.set_path_to_level(root, graft_level, group))
        parent_path = os.path.dirname(levelled_name)
        parent_node = self.ensure_parent_exists(parent_path)

        # Detach from the old parent and graft to the new location
        self.detach_node(current_node)
        current_node.name = levelled_name
        parent_node.add_child(current_node)
        current_node.path = root

        # Rename and relevel child nodes
        self.rename_children(current_node, levelled_name)
        
        # Prune old parent node if empty
        node_to_check = current_node_parent
        while node_to_check and node_to_check != self.root:
            if not node_to_check.images and not node_to_check.children:
                parent = node_to_check.parent
                if parent:
                    parent.children = [child for child in parent.children if child != node_to_check]
                # Remove from node_lookup if you want to keep it clean
                if node_to_check.name in self.node_lookup:
                    del self.node_lookup[node_to_check.name]
                node_to_check = parent
            else:
                break

    def rename_children(self, parent_node, new_parent_name):
        """
        Traverse the subtree of the parent node and update the names
        of all child nodes to reflect the graft. Assumes levels are calculated dynamically.

        Args:
            parent_node (TreeNode): The grafted node whose children need updating.
            new_parent_name (str): The new name of the parent node after grafting.
        """
        for child in parent_node.children:
            # Calculate the new name for the child node
            child_basename = os.path.basename(child.name)
            # old_name = child.name
            child.name = os.path.join(new_parent_name, child_basename)

            # Log the renaming
            # print(f"Updated node: {old_name} -> {child.name}")

            # Recursively update the child's subtree
            self.rename_children(child, child.name)

    def process_specific_images(self, specific_images, defaults):
        """
        Process specific images and add them to the tree.
        """
        num_average_images = int((lambda a, b: b / a)(*self.count_branches(self.root)))

        for path, data in specific_images.items():
            if filters.passes(path) == 0:
                node_name = path
                is_percentage = data.get("is_percentage", True)
                level = data.get("level", self.calculate_level(node_name))

                self.append_overwrite_or_update(
                    node_name,
                    level,
                    defaults.depth,
                    {
                        "weight_modifier": data.get("weight_modifier", 100),
                        "is_percentage": is_percentage,
                        "proportion" : data.get("proportion", None),
                        "images": [path] * (num_average_images if is_percentage else data.get("weight_modifier", 100)),
                    },
                )

                # Handle grafting after processing the directory
                graft_level = data.get("graft_level") or level
                group = data.get("group")
                if (graft_level is not None and graft_level != level) or (group):
                    self.handle_grafting(node_name, graft_level, group)

    def append_overwrite_or_update(self, path, level, depth, node_data=None):
        """
        Add or update a node in the tree. If the node already exists, overwrite or update it.
        """

        # # If a level override exists, truncate the path
        # if level is not None:
        #     path = self.set_path_to_level(path, level)

        # Convert path to match the format used in node_lookup
        tree_path = self.convert_path_to_tree_format(path)

        # Ensure all parent nodes exist
        tree_parent_name = self.find_parent_name(tree_path)
        # tree_parent_name = self.convert_path_to_tree_format(parent_name)
        self.ensure_parent_exists(tree_parent_name)

        # path_name = self.convert_path_to_tree_format(path)
        node = self.find_node(tree_path)
        if node:
            # Update node data if it exists
            node.weight_modifier = node_data["weight_modifier"]
            node.is_percentage = node_data["is_percentage"]
            node.proportion = node_data["proportion"]
            node.images.extend(node_data["images"])
        else:
            # Create a new node and add it to the tree
            new_node = TreeNode(
                name=tree_path,
                path=None,
                weight_modifier=node_data["weight_modifier"],
                is_percentage=node_data["is_percentage"],
                proportion=node_data["proportion"],
                images=node_data["images"],
            )
            self.add_node(new_node, tree_parent_name)

    def detach_node(self, node):
        """
        Detach a node from its parent and update parent/child relationships.

        Args:
            node (TreeNode): The node to be detached.
        """
        if node.parent:
            # Remove the node from its parent's children list
            node.parent.children = [child for child in node.parent.children if child != node]
            # Clear the node's parent reference
            node.parent = None

    def add_node(self, new_node, tree_parent_name):
        """
        Add a new node to the tree, ensuring the parent exists.

        Args:
            new_node (TreeNode): The node to be added.
            parent_name (str): The name of the parent node.

        Raises:
            ValueError: If the parent cannot be created or added for any reason.
        """
        # Ensure the parent exists

        # tree_parent_name = self.convert_path_to_tree_format(parent_name)
        # self.ensure_parent_exists(tree_parent_name)

        # Find the parent node
        parent_node = self.find_node(tree_parent_name)
        # if not parent_node:
        #     raise ValueError(f"Failed to create or find parent node '{parent_name}'.")

        # Add the new node to the parent
        parent_node.add_child(new_node)
        self.node_lookup[new_node.name] = new_node

    def ensure_parent_exists(self, parent_name):
        """
        Iteratively ensure all parent nodes exist from the root down to the specified parent_name.

        Args:
            parent_name (str): The full path of the parent node to ensure exists.
            return_parent (bool): If True, return the parent `TreeNode`.

        Returns:
            TreeNode: The parent node if `return_parent` is True, otherwise None.
        """
        path_components = parent_name.split(os.path.sep)
        current_path = "root"
        current_node = self.root

        for component in path_components[1:]:  # Skip the "root" component
            next_path = os.path.join(current_path, component)

            if next_path not in self.node_lookup:
                # Create the next node if it doesn't exist
                new_node = TreeNode(name=next_path, path=None)
                current_node.add_child(new_node)
                self.node_lookup[next_path] = new_node
                current_node = new_node
            else:
                # Move to the existing node
                current_node = self.node_lookup[next_path]

            current_path = next_path

        return current_node

    def convert_path_to_tree_format(self, path):
        """
        Convert the path to match the format used in node_lookup (e.g., prefixed with 'root').
        Removes the drive letter and adds 'root' as the base.
        """
        # Remove the drive letter (e.g., "I:") from the path
        path_without_drive = os.path.splitdrive(path)[1]

        # Split the path into components and prepend "root"
        path_components = ["root"] + path_without_drive.strip(os.path.sep).split(os.path.sep)

        # Join the components back into a single path
        return os.path.join(*path_components)

    def set_path_to_level(self, path, level, group = None):
        """
        Adjust the path to the specified level. If the level is less than the current level, truncate the path.
        If the level is greater than the current level, extend the path with placeholder folders.

        Args:
            path (str): The original path.
            level (int): The target level for the path.

        Returns:
            str: The adjusted path.
        """
        current_level = self.calculate_level(path)
        path_components = path.split(os.path.sep)

        # Normalize the drive component
        if len(path_components) > 0 and path_components[0].endswith(":"):
            path_components[0] += os.path.sep
        # Remove any empty components
        if group:
            extension_root = group
            for i in range(1, len(path_components) - 1):
                path_components[i] = f"{extension_root}_{i}"

        else:
            path_components = list(filter(lambda x: x != '', path_components))
            extension_root = "unamed"

        if level <= current_level:
            # Truncate the path
            truncated_components = path_components[:level - 1] + path_components[len(path_components) - 1:]
            return os.path.join(*truncated_components)

        elif level > current_level:
            # Extend the path with placeholders
            extension = [f"{extension_root}_{i - 1}" for i in range(current_level, level)]
            extended_components = path_components[:-1] + extension + [path_components[-1]]
            return os.path.join(*extended_components)

        # No adjustment needed
        return path

    def find_parent_name(self, node_name):
        """
        Find the name of the parent node.

        Args:
            node_name (str): The name of the current node.

        Returns:
            str: The name of the parent node.
        """
        return os.path.dirname(node_name)

    def find_node(self, name):
        return self.node_lookup.get(name)

    def get_nodes_at_level(self, target_level):
        """
        Retrieve all nodes at a specific level, optimized to skip unnecessary traversal.

        Args:
            target_level (int): The level to retrieve nodes from.

        Returns:
            list: A list of TreeNode instances at the specified level.
        """
        nodes_at_level = []

        def traverse(node):
            if node.level == target_level:
                nodes_at_level.append(node)
                # Skip traversing children since this node is at the target level
                return
            for child in node.children:
                traverse(child)

        traverse(self.root)
        return nodes_at_level

    def calculate_level(self, path):
        return len(list(filter(None, path.split(os.path.sep))))  # Calculate level based on path depth

    def extract_image_paths_and_weights_from_tree(self, test_iterations=None):
        all_images = []
        weights = []

        # Helper function to recursively gather data
        def traverse_node(node):
            if not node:
                return

            # Number of images in this node
            number_of_images = len(node.images)
            if number_of_images != 0:
                normalised_weight = node.weight / (number_of_images if node.is_percentage else node.weight_modifier)

                # Add current node's images and normalized weights
                if test_iterations is None:
                    for img in node.images:
                        all_images.append(img)
                        weights.append(normalised_weight)
                else:
                    for img in node.images:
                        all_images.append(node.name)
                        weights.append(normalised_weight)                    

            # Recurse into children
            for child in node.children:
                traverse_node(child)

        # Start traversal from the root node
        traverse_node(self.root)

        return all_images, weights

    def count_branches(self, node):
        """
        Recursively count the number of branches and images in the tree.

        Args:
            node (TreeNode): The current node.

        Returns:
            tuple: (branch_count, image_count) where:
                - branch_count is the total number of branches.
                - image_count is the total number of images.
        """
        if not node:
            return 0, 0

        branch_count = 0
        image_count = 0

        # Count current node as a branch if it has images
        if node.images:
            branch_count = 1
            image_count = len(node.images)

        # Recursively count branches and images in child nodes
        for child in node.children:
            child_branch_count, child_image_count = self.count_branches(child)
            branch_count += child_branch_count
            image_count += child_image_count

        return branch_count, image_count

    def calculate_branch_weights(self, mode="plain", balance_level=None, node=None, total_weight=TOTAL_WEIGHT):
        """
        Recursively calculates and normalizes the total weight for each branch in the tree,
        ensuring weights are divided horizontally across siblings.

        Args:
            mode (str): Weighting mode. Options are "plain", "balanced", "weighted_x".
            balance_level (int): Used for "weighted_x" mode. Specifies the level to start weighting from.
            node (TreeNode): The current node to calculate weights for. Defaults to the root node.
            total_weight (float): Total weight to distribute (defaults to 100%).

        Returns:
            float: The total weight for the current branch.
        """

        def fill_missing_proportions(nodes):
            """
            Receives a list of nodes, calculates and fills missing proportions,
            and returns the updated list.
            """
            # Calculate the sum of already set proportions
            total_set_proportion = sum(
                node.proportion for node in nodes if node.proportion is not None
            )
            # Find nodes with no set proportion
            unset_nodes = [node for node in nodes if node.proportion is None]
            num_unset = len(unset_nodes)

            # Distribute remaining proportion equally among unset nodes
            remaining = max(0, 100 - total_set_proportion)
            proportion_per_node = remaining / num_unset if num_unset > 0 else 0

            for node in unset_nodes:
                node.proportion = proportion_per_node

            return nodes

        if node is None:
            node = self.root
        """ TODO:
                Implement secondary modes
        """
        if mode == "flat":
            for child in node.children:
                self.calculate_branch_weights(mode, balance_level, child, total_weight)
        elif mode == "balanced":
            # Weight only starts balancing at level X
            if node.level < balance_level - 1:
                # Propagate weights without dividing
                for child in node.children:
                    self.calculate_branch_weights("balanced", balance_level, child, total_weight)
            elif node.level == balance_level - 1:
                children = self.get_nodes_at_level(balance_level)
                # Treat as a new subtree
                
                children = fill_missing_proportions(children)
                for child in children:
                    self.calculate_branch_weights("balanced", balance_level, child, total_weight * (child.proportion / 100))
            elif node.level >= balance_level:
                node.children = fill_missing_proportions(node.children)
                for child in node.children:
                    self.calculate_branch_weights("balanced", balance_level, child, total_weight * (child.proportion / 100))
        elif mode == "weighted":
            # Weight only starts balancing at level X
            if node.level >= balance_level:
                # Treat as a new subtree
                child_weight = total_weight
                for child in node.children:
                    self.calculate_branch_weights("weighted", balance_level, child, child_weight / len(node.children))
            else:
                # Propagate weights without dividing
                for child in node.children:
                    self.calculate_branch_weights("weighted", balance_level, child, total_weight)

        elif mode == "plain":
            for children in node.children:
                self.calculate_branch_weights(mode=mode, balance_level=balance_level, node=children, total_weight=total_weight / len(node.children))

        # Assign the calculated weight to the current node
        if node.is_percentage:
            node.weight = total_weight * (node.weight_modifier / 100)
        else:
            node.weight = total_weight

    def print_tree(self, node=None, indent="", current_depth=0, max_depth=None):
        """
        Recursively prints the tree in an ASCII hierarchical format.
        """
        if node is None:
            node = self.root

        if max_depth is not None and current_depth > max_depth:
            return

        num_images = len(node.images) if node.images else 0
        if num_images == 0:
            # ANSI escape code for dark grey: \033[90m ... \033[0m
            percent_sign = "%" if node.is_percentage else ""
            print(f"\033[90m{indent}{node.name} (L: {node.level}, P: {node.proportion}, M: {node.weight_modifier}{percent_sign}, W: {node.weight})\033[0m")
        else:
            percent_sign = "%" if node.is_percentage else ""
            print(f"{indent}{node.name} (L: {node.level}, P: {node.proportion}, M: {node.weight_modifier}{percent_sign}, W: {node.weight}, Images: {num_images})")

        for child in node.children:
            self.print_tree(child, indent + " + ", current_depth + 1, max_depth)

class Defaults:
    def __init__(
        self, weight_modifier=100, mode=("balanced", 1), depth=9999, is_random=False, args=None
    ):
        self._weight_modifier = weight_modifier
        self._mode = mode
        self._depth = depth
        self._is_random = is_random

        self.global_mode = None
        self.global_depth = None
        self.global_is_random = None

        self.args_mode = args.mode if args and args.mode is not None else None
        self.args_depth = args.depth if args and args.depth is not None else None
        self.args_is_random = args.random if args and args.random is not None else None

    @property
    def weight_modifier(self):
        return self._weight_modifier

    @property
    def mode(self):
        if self.args_mode is not None:
            return self.args_mode
        elif self.global_mode is not None:
            return self.global_mode
        else:
            return self._mode

    @property
    def depth(self):
        if self.args_depth is not None:
            return self.args_depth
        elif self.global_depth is not None:
            return self.global_depth
        else:
            return self._depth

    @property
    def is_random(self):
        if self.args_is_random is None:
            return self.args_is_random
        elif self.global_is_random is not None:
            return self.global_is_random
        else:
            return self._is_random

    def set_global_defaults(self, mode=None, depth=None, is_random=None):
        if mode is not None:
            self.global_mode = mode
        if depth is not None:
            self.global_depth = depth
        if is_random is not None:
            self.global_is_random = is_random

    def set_args_defaults(self, mode=None, depth=None, is_random=None):
        if mode is not None:
            self.args_mode = mode
        if depth is not None:
            self.args_depth = depth
        if is_random is not None:
            self.args_is_random = is_random

class Filters:
    def __init__(self):
        self.must_contain = set()
        self.must_not_contain = set()
        self.ignored_dirs = set()
        self.ignored_files = set()

    def add_must_contain(self, keyword):
        self.must_contain.add(keyword)

    def add_must_not_contain(self, keyword):
        self.must_not_contain.add(keyword)

    def add_ignored_dir(self, directory):
        self.ignored_dirs.add(directory)
        
    def add_ignored_file(self, file):
        self.ignored_files.add(file)

    def passes(self, path):
        if any(os.path.normpath(path) == os.path.normpath(ignored_dir)
                for ignored_dir in self.ignored_dirs):
            return 1

        if any(keyword in path for keyword in self.must_not_contain):
            return 2

        if self.must_contain and not any(
            keyword in path for keyword in self.must_contain
        ):
            return 2

        return 0

class Stack:
    def __init__(self, max_size=None):
        """
        Initialize a new Stack.

        Args:
            max_size (int, optional): The maximum number of items the stack can hold.
                                      If None, the stack size is unlimited.
        """
        self.max_size = max_size
        self.stack = []

    def push(self, root, listA, listB):
        """
        Push a pair of lists onto the stack.

        Args:
            listA (list): The first list to be pushed onto the stack.
            listB (list): The second list to be pushed onto the stack.
        """
        if self.max_size is None or len(self.stack) < self.max_size:
            self.stack.append((root, listA, listB))
        else:
            print("Stack is full. Cannot push more items.")

    def pop(self):
        """
        Pop the top pair of lists off the stack.

        Returns:
            tuple: A tuple containing the two lists that were on top of the stack.
        """
        if self.stack:
            return self.stack.pop()
        else:
            print("Stack is empty. Cannot pop items.")
            return None, None, None  # Return empty lists if the stack is empty
        
    def read_top(self, index=1):
        if self.stack:
            return self.stack[len(self.stack)-index][0]

    def clear(self):
        """Clear the stack."""
        self.stack.clear()

    def len(self):
        return len(self.stack)

    def is_empty(self):
        """Check if the stack is empty."""
        return len(self.stack) == 0

    def is_full(self):
        """Check if the stack is full."""
        if self.max_size is None:
            return False
        return len(self.stack) >= self.max_size

# Utility functions
def level_of(path):
    return len([item for item in path.split(os.sep) if item != ""])

def truncate_path(path, levels_up):
    """Truncate the path based on the balance level."""
    return "\\".join(
        path.split("\\")[
            : ((level_of(path) - levels_up) if levels_up < 0 else levels_up)
        ]
    )

def contains_subdirectory(path):
    for root, directories, files in os.walk(path):
        if directories:
            return len(directories)
    return False

def contains_files(path):
    for root, directories, files in os.walk(path):
        if files:
            return True
    return False

def is_textfile(file):
    return file.lower().endswith(TEXT_FILES)
    
def is_imagefile(file):
    return file.lower().endswith(IMAGE_FILES)

def test_distribution(image_nodes, weights, iterations, testdepth, defaults):
    hit_counts = defaultdict(int)
    for _ in tqdm(range(iterations), desc="Iterating tests"):
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

def find_input_file(input_filename, additional_search_paths=[]):
    # List of potential directories to search
    possible_locations = [
        os.path.dirname(os.path.abspath(__file__)),  # Script's directory
        os.getcwd(),  # Current working directory
        *additional_search_paths,  # Additional paths (e.g., main input file's directory)
        os.path.join(os.getcwd(), 'lists'),  # Fixed "lists" folder in the current working directory
    ]
    
    for location in possible_locations:
        potential_path = os.path.join(location, input_filename)
        if os.path.isfile(potential_path):
            return potential_path

    return None

def parse_input_line(line, defaults, recdepth):
    modifier_pattern = re.compile(r"(\[.*?\])")
    weight_modifier_pattern = re.compile(r"^\d+%?$")
    proportion_pattern = re.compile(r"^%\d+%?$")
    balance_pattern = re.compile(r"^b\d+$", re.IGNORECASE)
    graft_pattern = re.compile(r"^g\d+$", re.IGNORECASE)
    group_pattern = re.compile(r"^>.*", re.IGNORECASE)
    depth_pattern = re.compile(r"^d\d+$", re.IGNORECASE)
    flat_pattern = re.compile(r"^f$", re.IGNORECASE)

    if line.startswith("[r]"):
        defaults.set_global_defaults(is_random=True)
        return None, None

     # Handle filters
    if line.startswith("[+]"):
        keyword = line[3:].strip()
        filters.add_must_contain(keyword)
        return None, None
    elif line.startswith("[-]"):
        path_or_keyword = line[3:].strip()
        if os.path.isabs(path_or_keyword):
            if os.path.isfile(path_or_keyword):
                filters.add_ignored_file(path_or_keyword)
            else:
                filters.add_ignored_dir(path_or_keyword)
        else:                
            filters.add_must_not_contain(path_or_keyword)
        return None, None

    # Initialize default modifiers
    weight_modifier = 100
    proportion = None
    is_percentage = True
    graft_level = None
    group = None
    balance_level = defaults.mode[1]
    depth = defaults.depth
    flat = False

    # Extract all modifiers
    modifiers = modifier_pattern.findall(line)
    # Remove all modifiers from the line to get the path
    path = modifier_pattern.sub("", line).strip()

    # Process each modifier
    for mod in modifiers:
        mod_content = mod.strip("[]").strip()
        if weight_modifier_pattern.match(mod_content):
            # Weight modifier
            if mod_content.endswith("%"):
                weight_modifier = int(mod_content[:-1])
                is_percentage = True
            else:
                weight_modifier = int(mod_content)
                is_percentage = False
        elif proportion_pattern.match(mod_content):
            # Proportion
            proportion = int(mod_content[1:-1])
        elif graft_pattern.match(mod_content):
            # Graft level modifier
            graft_level = int(mod_content[1:])
        elif graft_pattern.match(mod_content):
            # Level modifier
            graft_level = int(mod_content[1:])
        elif group_pattern.match(mod_content):
            # Group
            group = mod_content[1:]
        elif balance_pattern.match(mod_content):
            # Balance level modifier, global only
            balance_level = int(mod_content[1:])
        elif depth_pattern.match(mod_content):
            # Depth modifier
            depth = int(mod_content[1:])
        elif flat_pattern.match(mod_content):
            flat = True
        else:
            print(f"Unknown modifier '{mod_content}' in line: {line}")

    # Handle directory or specific image
    if path == "*" and recdepth == 1:
        defaults.set_global_defaults(
            mode=("balanced", balance_level), depth=depth
        )
        return None, None
    
    if os.path.isdir(path):
        return path, {
            "weight_modifier": weight_modifier,
            "is_percentage": is_percentage,
            "proportion": proportion,
            "graft_level": graft_level,
            "group": group,
            "depth": depth,
            "flat": flat,
        }
    elif os.path.isfile(path):
        return path, {
            "weight_modifier": weight_modifier,
            "is_percentage": is_percentage,
            "proportion": proportion,
            "graft_level": graft_level,
            "group": group
        }
    else:
        print(f"Path '{path}' is neither a file nor a directory.")

    return None, None

def process_inputs(input_files, defaults, recdepth=1):
    """
    Parse input files and directories to create image_dirs and specific_images dictionaries.

    Args:
        input_files (list): List of input files or directories.
        defaults (object): Defaults object containing configuration.

    Returns:
        tuple: (image_dirs, specific_images)
    """
    image_dirs = {}
    specific_images = {}

    def process_entry(entry):
        """Process a single input entry (file, directory, or image)."""
        nonlocal image_dirs, specific_images

        if is_textfile(entry):  # If it's a text file, parse its contents
            additional_search_paths = [os.path.dirname(entry)]
            input_filename_full = find_input_file(entry, additional_search_paths)

            if input_filename_full:
                with open(input_filename_full, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):  # Skip comments/empty lines
                            continue
                        line = line.replace('"', "").strip()  # Remove enclosing quotes

                        if is_textfile(line):  # Recursively process nested text files
                            sub_image_dirs, sub_specific_images = process_inputs([line], defaults, recdepth+1)
                            image_dirs.update(sub_image_dirs)
                            specific_images.update(sub_specific_images)
                        else:
                            path, modifier_list = parse_input_line(line, defaults, recdepth)
                            if modifier_list:
                                if is_imagefile(path):
                                    specific_images[path] = modifier_list
                                else:
                                    image_dirs[path] = modifier_list

        else:  # Handle directories and images directly
            path, modifier_list = parse_input_line(entry, defaults, recdepth)
            if modifier_list:
                if is_imagefile(path):
                    specific_images[path] = modifier_list
                else:
                    image_dirs[path] = modifier_list

    # Process each entry in the input list
    for input_entry in input_files:
        process_entry(input_entry)

    return image_dirs, specific_images

def start_slideshow(all_image_paths, weights, tree, defaults):
    """
    Start the slideshow using the given paths and weights.

    Args:
        all_image_paths (list): List of image paths.
        weights (list): List of weights corresponding to image paths.
        tree (Tree): Tree object containing the image hierarchy.
        defaults (object): Defaults object containing configuration.
    """
    import tkinter as tk
    root = tk.Tk()
    slideshow = ImageSlideshow(root, all_image_paths, weights, tree, defaults)  # noqa: F841
    root.mainloop()


def main(input_files, defaults, test_iterations=None, testdepth=None, printtree=None):
    # Parse input files and directories
    image_dirs, specific_images = process_inputs(input_files, defaults)

    if not image_dirs and not specific_images:
        raise ValueError("No images found in the provided directories and specific images.")

    # Instantiate and build the tree
    tree = Tree()
    tree.build_tree(image_dirs, specific_images, defaults)
    tree.calculate_branch_weights(mode=defaults.mode[0], balance_level=defaults.mode[1])

    # Print tree if requested
    if printtree:
        tree.print_tree(max_depth=testdepth)
        return

    # Extract paths and weights from the tree
    all_images, weights = tree.extract_image_paths_and_weights_from_tree(test_iterations)

    # Test or start the slideshow
    if test_iterations:
        test_distribution(all_images, weights, test_iterations, testdepth, defaults)
    else:
        start_slideshow(all_images, weights, tree, defaults)

if __name__ == "__main__":
    defaults = Defaults(args=args)
    filters = Filters()

    # Use args.input_file directly as a list
    input_files = args.input_file if args.input_file else []

    if args.run:
        main(input_files, defaults)
    elif args.printtree:
        main(input_files, defaults, testdepth=args.testdepth, printtree=True)
    elif args.test:
        main(
            input_files,
            defaults,
            test_iterations=args.test,
            testdepth=args.testdepth if args.testdepth else defaults.depth + 1,
        )