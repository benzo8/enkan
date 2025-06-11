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
    default=("weighted", 0),
    help="Set the mode: (weighted) or (balanced [x])",
)
parser.add_argument(
    "--depth",
    type=int,
    default=9999,
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
    def __init__(self, root, image_paths, weights, is_random):
        self.root = root
        self.image_paths = image_paths
        self.weights = weights
        self.original_image_paths = image_paths
        self.number_of_images = len(image_paths)
        self.current_image_index = 0
        self.original_weights = weights
        self.history = deque(maxlen=10)
        self.forward_history = deque(maxlen=10)
        self.subfolder_mode = False
        self.show_filename = False

        self.screen_width = root.winfo_screenwidth()
        self.screen_height = root.winfo_screenheight()

        self.initial_mode = mode
        if is_random:
            self.mode, self.mode_level = ("random", mode[1])
        else:
            self.mode, self.mode_level = mode

        self.rotation_angle = 0

        self.root.configure(background="black")  # Set root background to black
        self.label = tk.Label(root, bg="black")  # Set label background to black
        self.label.pack()

        self.filename_label = tk.Label(self.root, bg="black", fg="white", anchor="nw")
        self.mode_label = tk.Label(self.root, bg="black", fg="white", anchor="ne")

        self.root.attributes("-fullscreen", True)
        self.root.bind("<space>", self.next_image)
        self.root.bind("<Escape>", self.exit_slideshow)
        self.root.bind("<Left>", self.previous_image)
        self.root.bind("<Right>", self.next_image_forward)
        self.root.bind("<Delete>", self.delete_image)
        self.root.bind("<s>", self.toggle_subfolder_mode)
        self.root.bind("<n>", self.toggle_filename_display)
        self.root.bind("<r>", self.toggle_random_mode)
        self.root.bind("<o>", self.rotate_image)
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

    def toggle_subfolder_mode(self, event=None):
        if not self.subfolder_mode:
            current_dir = os.path.dirname(self.current_image_path)
            self.image_paths = [
                path
                for path in self.original_image_paths
                if path.startswith(current_dir)
            ]
            self.weights = [
                self.original_weights[i]
                for i, path in enumerate(self.original_image_paths)
                if path.startswith(current_dir)
            ]
            self.number_of_images = len(
                self.image_paths
            )  # Update the number of images for the subfolder
            self.current_image_index = (
                0  # Reset the current image index for the subfolder
            )
            self.subfolder_mode = True
        else:
            self.image_paths = self.original_image_paths
            self.weights = self.original_weights
            self.number_of_images = len(
                self.image_paths
            )  # Update the number of images for the full set
            self.current_image_index = self.image_paths.index(
                self.current_image_path
            )  # Update to the current image index
            self.subfolder_mode = False
        self.show_image(self.current_image_path)
        self.update_filename_display()

    def toggle_filename_display(self, event=None):
        self.show_filename = not self.show_filename
        self.update_filename_display()

    def update_filename_display(self):
        if self.show_filename:
            filename_text = f"{self.current_image_path}"
            self.filename_label.config(text=filename_text)
            self.filename_label.place(x=0, y=0)

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

    def truncate_path(self, path):
        """Truncate the path based on the balance level."""
        return "\\".join(path.split("\\")[: self.balance_level])

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

    def append_overwrite_or_update(self, full_branch_path, depth, data):
        """Append, overwrite, or update a branch based on the full branch path, with support for virtual folders."""
        # Automatically determine the trunk based on the balance level
        trunk = self.truncate_path(full_branch_path)

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

    def build_image_paths_and_weights(self):
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


def parse_input_file(input_file):
    image_dirs = {}
    specific_images = {}
    filters = {
        "must_contain": [],  # List of keywords that must be present in the path
        "must_not_contain": [],  # List of keywords that must NOT be present in the path
        "ignored_dirs": [],  # List of absolute directories to ignore
    }

    default_weight = 100
    default_is_percentage = True
    default_balance = args.mode[1] if args.mode else 1
    default_depth = args.depth if args.depth else 9999

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

            # Handle subfile inclusion
            if line.startswith("[l]"):
                subfile = line[3:].strip()
                if os.path.isfile(subfile):
                    sub_image_dirs, sub_specific_images, sub_filters = parse_input_file(
                        subfile
                    )
                    image_dirs.update(sub_image_dirs)
                    for k, v in sub_specific_images.items():
                        specific_images[k].update(v)
                    for key in filters:
                        filters[key].extend(sub_filters[key])
                    specific_images.update(sub_specific_images)
                continue  # Move to the next line after processing subfile

            # Handle filters
            if line.startswith("[-]"):
                path_or_keyword = line[3:].strip()
                if os.path.isabs(path_or_keyword):
                    filters["ignored_dirs"].append(path_or_keyword)
                else:
                    filters["must_not_contain"].append(path_or_keyword)
                continue

            if line.startswith("[+]"):
                keyword = line[3:].strip()
                filters["must_contain"].append(keyword)
                continue

            # Initialize default modifiers
            weight = default_weight
            is_percentage = default_is_percentage
            balance_level = default_balance
            depth = default_depth

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
            if os.path.isdir(path):
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

    return image_dirs, specific_images, filters


def test_filters(path, filters):
    # Check if the path is in the ignored_dirs
    if any(
        os.path.normpath(path) == os.path.normpath(ignored_dir)
        for ignored_dir in filters["ignored_dirs"]
    ):
        return 1

    # Check must_not_contain keywords
    if any(keyword in path for keyword in filters["must_not_contain"]):
        return 2

    # Check must_contain keywords
    if filters["must_contain"] and not any(
        keyword in path for keyword in filters["must_contain"]
    ):
        return 2

    return 0


def calculate_weights(
    folder_data, specific_images, filters, mode, depth
):
    """
    Calculate weights of all images in folders in folders_data, and specified_images
    """

    all_image_paths = []
    weights = []

    if mode[0] == "weighted":
        mode = ("balanced", 1)

    # Assign weights to image folders
    mode_depth = mode[1]

    tree = Tree(mode_depth)

    for path, data in folder_data.items():
        depth = data["depth"] or depth
        for root, dirs, files in os.walk(path):
            result = test_filters(root, filters)
            if result == 0:
                images = [
                    os.path.join(root, f)
                    for f in files
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp"))
                ]
                if images:
                    tree.append_overwrite_or_update(
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
        num_average_images = int(tree.average_images_in_tree())
        for path, data in specific_images.items():
            is_percentage = data["is_percentage"]
            tree.append_overwrite_or_update(
                path,
                depth,
                {
                    "weight": data["weight"],
                    "is_percentage": data["is_percentage"],
                    "images": [path]
                    * (num_average_images if is_percentage else data["weight"]),
                },
            )

    all_image_paths, weights = tree.build_image_paths_and_weights()

    return all_image_paths, weights


def test_distribution(
    image_paths, weights, iterations, testdepth, is_random=False
):
    hit_counts = defaultdict(int)
    for _ in range(iterations):
        if is_random:
            image_path = random.choice(image_paths)
        else:
            image_path = random.choices(image_paths, weights=weights, k=1)[0]
        hit_counts["\\".join(image_path.split("\\")[:testdepth])] += 1

    # directory_counts = defaultdict(int)
    # for path, count in hit_counts.items():
    #     directory = os.path.dirname(path)
    #     directory_counts[directory] += count

    total_images = len(image_paths)
    for directory, count in sorted(hit_counts.items()):  # Alphabetical order
        print(
            f"Directory: {directory}, Hits: {count}, Weight: {count / total_images * TOTAL_WEIGHT:.2f}"
        )


def main(
    input_files,
    test_iterations=None,
    testdepth=None,
    is_random=False,
):
    start_time = time.time()

    image_dirs = {}
    specific_images = {}
    filters = {
        "must_contain": [],  # List of keywords that must be present in the path
        "must_not_contain": [],  # List of keywords that must NOT be present in the path
        "ignored_dirs": [],  # List of absolute directories to ignore
    }

    for input_filename in input_files:
        if os.path.isfile(input_filename):
            sub_image_dirs, sub_specific_images, sub_filters = parse_input_file(
                input_filename
            )
            image_dirs.update(sub_image_dirs)
            specific_images.update(sub_specific_images)
            for key in sub_filters:
                filters[key].extend(sub_filters[key])

    if not image_dirs and not specific_images:
        raise ValueError(
            "No images found in the provided directories and specific images."
        )
        sys.exit()
    all_image_paths, weights = calculate_weights(
        image_dirs, specific_images, filters
    )

    if test_iterations:
        test_distribution(
            all_image_paths, weights, test_iterations, testdepth, is_random
        )
    else:
        root = tk.Tk()
        slideshow = ImageSlideshow(  # noqa: F841
            root, all_image_paths, weights, is_random
        )  # noqa: F841
        root.mainloop()

    print("Finished --- %s seconds ---" % (time.time() - start_time))


if __name__ == "__main__":
    
    if args.run:
        input_files = args.input_file.split("+") if args.input_file else []
        main(
            input_files,
            is_random=args.random,
        )
    elif args.test:
        input_files = args.input_file.split("+") if args.input_file else []
        main(
            input_files,
            test_iterations=args.test,
            testdepth=args.testdepth if args.testdepth else args.depth,
            is_random=args.random,
        )
