import argparse
import os
import random
import re
import sys
import time
import tkinter as tk
from collections import defaultdict, deque
from tkinter import messagebox

from PIL import Image, ImageTk

# Constants
TOTAL_WEIGHT = 1000000
PARENT_STACK_MAX = 5
QUEUE_LENGTH_MAX = 10


# Argument parsing setup
class ModeAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if len(values) == 1:
            if values[0] not in ["weighted", "balanced"]:
                parser.error(
                    f"Invalid choice: '{values[0]}'. Choose from 'weighted', 'balanced'."
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
    nargs="?",
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

    def follow_branch_down(self, event=None):
        """Move down one level in the tree and update the slideshow."""
        
        if self.parentFolderStack.is_full(): # Test for S0                         
            print("S0 - Doing nothing")
            return    
            
        if self.subfolder_mode and self.parent_mode: # S4
            self.subfolder_mode_off()
            self.show_image(self.current_image_path)
            self.update_filename_display()
            return
                        
        if not self.parent_mode: # S2
            current_path = os.path.dirname(self.current_image_path)
            current_path_level = level_of(current_path)
            for i in range(current_path_level - 1, 1, -1):             
                parent_level = i
                parent_path = truncate_path(current_path, parent_level)
                if contains_subdirectory(parent_path) > 1 or contains_files:
                    break
                
            self.parentFolderStack.push(
                parent_path, self.original_image_paths, self.original_weights
            )
        else: # S3
            previous_path = self.parentFolderStack.read_top()
            parent_level = level_of(previous_path) - 1
            parent_path = truncate_path(previous_path, parent_level)
            if parent_path == self.parentFolderStack.read_top(2):
                self.step_backwards()
                return
            
            self.parentFolderStack.push(parent_path, self.image_paths, self.weights)

        if os.path.isdir(parent_path):

            parent_image_dirs = {}
            self.image_paths = []
            self.weights = []

            parent_tree = Tree(defaults.mode[1])
            parent_image_dirs[parent_path] = {
                "weight": 100,
                "is_percentage": True,
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
                    "weight": 100,
                    "is_percentage": True,
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


class Tree:
    def __init__(self, balance_level):
        self.balance_level = balance_level  # Store the balance level
        self.trunks = {}  # Dictionary to store multiple trunks

    def add_trunk(self, trunk):
        """Add a new trunk if it doesn't exist."""
        if trunk not in self.trunks:
            self.trunks[trunk] = {}

    def extract_trunk(self, trunk):
        """Extract the specified trunk."""
        return self.trunks.get(trunk, None)

    def extract_branch(self, trunk, branch_path):
        """Extract a specific branch from a specific trunk."""
        if trunk in self.trunks:
            return self.trunks[trunk].get(branch_path, None)
        return None

    def get_parent_branch(self, path, levels_up=1):
        """Retrieve all branches at a parent level."""
        truncated_path = truncate_path(path, levels_up)
        parent_branch = self.extract_trunk(truncated_path)
        return parent_branch

    def append_overwrite_or_update(self, full_branch_path, depth, data):
        """Append, overwrite, or update a branch based on the full branch path, with support for virtual folders."""
        # Automatically determine the trunk based on the balance level
        trunk = truncate_path(full_branch_path, self.balance_level)

        # Ensure the trunk exists
        self.add_trunk(trunk)

        # Determine the depth of the current branch
        current_depth = len(full_branch_path.split("\\"))

        # If the current depth is at or above the specified depth, move to a virtual folder
        if current_depth >= depth:
            virtual_folder = self.trunks[trunk].setdefault(
                "virtual-folder",
                {"weight": data["weight"], "is_percentage": True, "images": []},
            )
            virtual_folder["images"].extend(data.get("images", []))
            # virtual_folder["weight"] += data["weight"]  # Optionally adjust the weight based on the new data
            virtual_folder["is_percentage"] = (
                virtual_folder["is_percentage"] or data["is_percentage"]
            )
        else:
            # If the branch exists, update the data; otherwise, add the new branch
            if full_branch_path in self.trunks[trunk]:
                existing_data = self.trunks[trunk][full_branch_path]
                existing_data.update(data)
                self.trunks[trunk][full_branch_path] = existing_data
            else:
                self.trunks[trunk][full_branch_path] = data

        # Handle small folders
        if len(data.get("images", [])) < 25 and current_depth < depth:
            small_folder = self.trunks[trunk].setdefault(
                "small-folder",
                {"weight": data["weight"], "is_percentage": True, "images": []},
            )
            small_folder["images"].extend(data.get("images", []))
            # small_folder["weight"] += data["weight"]  # Optionally adjust the weight based on the new data
            small_folder["is_percentage"] = (
                small_folder["is_percentage"] or data["is_percentage"]
            )

    def branches_in_trunk(self, trunk):
        """Return the number of branches within a given trunk."""
        branches = self.extract_trunk(trunk)
        return len(branches) if branches else 0

    def leaves_in_branch(self, trunk, branch_path):
        """Return the number of leaves (images) within a given branch."""
        branch = self.extract_branch(trunk, branch_path)
        return len(branch.get("images", [])) if branch else 0

    def average_images_in_trunk(self, trunk):
        """Calculate the average number of images in a trunk."""
        branches = self.extract_trunk(trunk)
        if not branches:
            return 0  # Return 0 if there are no branches in the trunk

        total_images = sum(
            len(branch_data.get("images", [])) for branch_data in branches.values()
        )
        num_branches = len(branches)

        return total_images / num_branches if num_branches > 0 else 0

    def average_images_in_tree(self):
        """Calculate the average number of images across the entire tree."""
        total_images = 0
        total_branches = 0

        for trunk, branches in self.trunks.items():
            for branch_data in branches.values():
                total_images += len(branch_data.get("images", []))
                total_branches += 1
        return total_images / total_branches if total_branches > 0 else 0

    def build_tree(self, image_dirs, specific_images, defaults):
        """
        Read image_dirs and specific_images and build a tree
        """
        # Assign weights to image folders

        for path, data in image_dirs.items():
            depth = data["depth"] or defaults.depth
            for root, dirs, files in os.walk(path):
                result = filters.passes(root)
                if result == 0:
                    images = [
                        os.path.join(root, f)
                        for f in files
                        if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp"))
                    ]
                    if images:
                        self.append_overwrite_or_update(
                            root,
                            depth,
                            {
                                "weight": data["weight"],
                                "is_percentage": data["is_percentage"],
                                "images": images,
                            },
                        )
                elif result == 1:
                    del dirs[:]

        if specific_images:
            num_average_images = int(self.average_images_in_tree())
            for path, data in specific_images.items():
                is_percentage = data["is_percentage"]
                self.append_overwrite_or_update(
                    path,
                    depth,
                    {
                        "weight": data["weight"],
                        "is_percentage": data["is_percentage"],
                        "images": [path]
                        * (num_average_images if is_percentage else data["weight"]),
                    },
                )

    def extract_image_paths_and_weights_from_tree(self):
        """Iterate through the tree to build all_image_paths and weights."""
        all_image_paths = []
        weights = []

        for trunk, branches in self.trunks.items():
            num_branches = len(branches)
            for branch, data in branches.items():
                image_list = data.get("images", [])

                is_percentage = data.get("is_percentage", True)
                if is_percentage:
                    number_of_images = len(image_list)
                    branch_weight = data.get("weight", 100) / 100

                else:
                    number_of_images = data.get("weight", 100)
                    branch_weight = 1
                normalised_weight = (
                    (TOTAL_WEIGHT / num_branches) / (number_of_images) * (branch_weight)
                )

                all_image_paths.extend(image_list)
                weights.extend([normalised_weight] * number_of_images)

        return all_image_paths, weights

    def print_tree(self):  # Utility method to print the tree structure (for debugging)
        for trunk, branches in self.trunks.items():
            print(f"Trunk: {trunk}")
            for branch, data in branches.items():
                print(f"  Branch: {branch}")
                for key, value in data.items():
                    print(f"    {key}: {value}")


class Defaults:
    def __init__(
        self, weight=100, mode=("weighted", 0), depth=9999, is_random=False, args=None
    ):
        self._weight = weight
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
    def weight(self):
        return self._weight

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
        self.must_contain = []
        self.must_not_contain = []
        self.ignored_dirs = []

    def add_must_contain(self, keyword):
        self.must_contain.append(keyword)

    def add_must_not_contain(self, keyword):
        self.must_not_contain.append(keyword)

    def add_ignored_dir(self, directory):
        self.ignored_dirs.append(directory)

    def passes(self, path):
        if any(
            os.path.normpath(path) == os.path.normpath(ignored_dir)
            for ignored_dir in self.ignored_dirs
        ):
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

def find_input_file(input_filename, additional_search_paths=[]):
    # List of potential directories to search
    possible_locations = [
        os.path.dirname(os.path.abspath(__file__)),  # Script's directory
        os.getcwd(),  # Current working directory
        *additional_search_paths,  # Additional paths (e.g., main input file's directory)
        os.path.join(os.getcwd(), 'config'),  # Fixed "config" folder in the current working directory
    ]
    
    for location in possible_locations:
        potential_path = os.path.join(location, input_filename)
        if os.path.isfile(potential_path):
            return potential_path

    return None

def parse_input_file(input_file, defaults):
    image_dirs = {}
    specific_images = {}

    modifier_pattern = re.compile(r"(\[.*?\])")
    weight_pattern = re.compile(r"^\d+%?$")
    balance_pattern = re.compile(r"^b\d+$", re.IGNORECASE)
    depth_pattern = re.compile(r"^d\d+$", re.IGNORECASE)

    with open(input_file, "r", encoding="utf-8") as f:
        content = f.readlines()
        for line in content:
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Remove enclosing double quotes, if any
            line = line.replace('"', "").strip()

            # Handle defaults declaration
            if line.startswith("[r]"):
                defaults.set_global_defaults(is_random=True)
                continue

            # Handle subfile inclusion
            if line.startswith("[l]"):
                subfile = line[3:].strip()
                if os.path.isfile(subfile):
                    sub_image_dirs, sub_specific_images = parse_input_file(
                        subfile, defaults
                    )
                    image_dirs.update(sub_image_dirs)
                    for k, v in sub_specific_images.items():
                        specific_images[k].update(v)
                continue  # Move to the next line after processing subfile

            # Handle filters
            if line.startswith("[+]"):
                keyword = line[3:].strip()
                filters.add_must_contain(keyword)
                continue
            elif line.startswith("[-]"):
                path_or_keyword = line[3:].strip()
                if os.path.isabs(path_or_keyword):
                    filters.add_ignored_dir(path_or_keyword)
                else:
                    filters.add_must_not_contain(path_or_keyword)
                continue

            # Initialize default modifiers
            weight = 100
            is_percentage = True
            balance_level = defaults.mode[1]
            depth = defaults.depth

            # Extract all modifiers
            modifiers = modifier_pattern.findall(line)
            # Remove all modifiers from the line to get the path
            path = modifier_pattern.sub("", line).strip()

            # Process each modifier
            for mod in modifiers:
                mod_content = mod.strip("[]").strip()
                if weight_pattern.match(mod_content):
                    # Weight modifier
                    if mod_content.endswith("%"):
                        weight = int(mod_content[:-1])
                        is_percentage = True
                    else:
                        weight = int(mod_content)
                        is_percentage = False
                elif balance_pattern.match(mod_content):
                    # Balance level modifier
                    balance_level = int(mod_content[1:])
                elif depth_pattern.match(mod_content):
                    # Depth modifier
                    depth = int(mod_content[1:])
                else:
                    print(f"Unknown modifier '{mod_content}' in line: {line}")

            # Handle directory or specific image
            if path == "*":
                defaults.set_global_defaults(
                    mode=("balanced", balance_level), depth=depth
                )
            elif os.path.isdir(path):
                image_dirs[path] = {
                    "weight": weight,
                    "is_percentage": is_percentage,
                    "balance_level": balance_level,
                    "depth": depth,
                }
            elif os.path.isfile(path):
                specific_images[path] = {
                    "weight": weight,
                    "is_percentage": is_percentage,
                    "balance_level": balance_level,
                    "depth": depth,
                }
            else:
                print(f"Path '{path}' is neither a file nor a directory.")

    return image_dirs, specific_images


def test_distribution(image_paths, weights, iterations, testdepth, defaults):
    hit_counts = defaultdict(int)
    for _ in range(iterations):
        if defaults.is_random:
            image_path = random.choice(image_paths)
        else:
            image_path = random.choices(image_paths, weights=weights, k=1)[0]
        hit_counts["\\".join(image_path.split("\\")[:testdepth])] += 1

    directory_counts = defaultdict(int)
    for path, count in hit_counts.items():
        if os.path.isfile(path):
            directory = os.path.dirname(path)
        else:
            directory = path
        directory_counts[directory] += count

    total_images = len(image_paths)
    for directory, count in sorted(directory_counts.items()):  # Alphabetical order
        print(
            f"Directory: {directory}, Hits: {count}, Weight: {count / total_images * TOTAL_WEIGHT:.2f}"
        )


def main(input_files, defaults, test_iterations=None, testdepth=None):
    start_time = time.time()

    image_dirs = {}
    specific_images = {}

    # Read input file(s) and create image_dirs and specific_images dictionaries

    for input_filename in input_files:
        additional_search_paths = [os.path.dirname(input_filename)]
        input_filename_full = find_input_file(input_filename, additional_search_paths)
        if input_filename_full:
            sub_image_dirs, sub_specific_images = parse_input_file(
                input_filename_full, defaults
            )
            image_dirs.update(sub_image_dirs)
            specific_images.update(sub_specific_images)
        else:
            print("Input file %T not found.", input_filename)

    if not image_dirs and not specific_images:
        raise ValueError(
            "No images found in the provided directories and specific images."
        )
        sys.exit()

    # ('weighted', x) is functionally identical to ('balanced', 1)
    if defaults.mode[0] == "weighted":
        mode = ("balanced", 1)
    else:
        mode = defaults.mode

    tree = Tree(mode[1])  # instantiate tree
    tree.build_tree(image_dirs, specific_images, defaults)

    # pull image paths and calculated weights lists from tree
    all_image_paths, weights = tree.extract_image_paths_and_weights_from_tree()
    print("Finished --- %s seconds ---" % (time.time() - start_time))

    if test_iterations:
        test_distribution(
            all_image_paths, weights, test_iterations, testdepth, defaults
        )
    else:
        root = tk.Tk()
        slideshow = ImageSlideshow(  # noqa: F841
            root, all_image_paths, weights, tree, defaults
        )  # noqa: F841
        root.mainloop()


if __name__ == "__main__":

    defaults = Defaults(args=args)
    filters = Filters()

    if args.run:
        input_files = args.input_file.split("+") if args.input_file else []
        main(input_files, defaults)
    elif args.test:
        input_files = args.input_file.split("+") if args.input_file else []
        main(
            input_files,
            defaults,
            test_iterations=args.test,
            testdepth=args.testdepth if args.testdepth else defaults.depth + 1,
        )
