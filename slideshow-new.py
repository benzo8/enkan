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
    "--total_weight",
    type=int,
    default=1000000,
    help="Total weight to be distributed among all images",
)
parser.add_argument(
    "--test", metavar="N", type=int, help="Run the test with N iterations"
)
parser.add_argument(
    "--testdepth", type=int, default=None, help="Depth to display test results"
)
args = parser.parse_args()


class ImageSlideshow:
    def __init__(self, root, image_paths, weights, mode, is_random):
        self.root = root
        self.image_paths = image_paths
        self.weights = weights
        self.original_image_paths = image_paths
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
            self.subfolder_mode = True
        else:
            self.image_paths = self.original_image_paths
            self.weights = self.original_weights
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

            if self.mode == "random":
                mode_text = "R"
            else:
                mode_text = "W" if self.mode == "weighted" else "B"
            if self.subfolder_mode:
                mode_text = "S"
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


def parse_input_file(input_file):
    """Read in input file(s)
    Interpret in-line modifiers

    Return:
        image_dirs - dictionary of top-level image directories, as per input files(s)
        specific_images - dictionary of individually specified images
        ignored_dirs - list of directories to be ignored
    """

    image_dirs = defaultdict(lambda: {"weight": 100, "is_absolute": False})
    specific_images = defaultdict(lambda: {"weight": 100, "is_absolute": False})
    ignored_dirs = []

    with open(input_file, "r", encoding="utf-8") as f:
        content = f.readlines()
        for line in content:
            line = line.replace('"', "").strip()
            if line.startswith("[l]"):
                subfile = os.path.join(os.path.split(input_file)[0], line[3:].strip())
                if os.path.isfile(subfile):
                    sub_image_dirs, sub_specific_images, sub_ignored_dirs = (
                        parse_input_file(subfile)
                    )
                    image_dirs.update(sub_image_dirs)
                    specific_images.update(sub_specific_images)
                    ignored_dirs.extend(sub_ignored_dirs)
            elif line.startswith("[-]"):
                ignored_dirs.append(line[3:].strip())
            elif os.path.isdir(line):
                image_dirs[line] = {"weight": 100, "is_absolute": False}
            else:
                matches = re.match(r"\[(\d+)(%?)\](.*)", line)
                if matches:
                    weight = int(matches[1])
                    is_percentage = matches[2] == "%"
                    path = matches[3].strip()
                    if os.path.isdir(path):
                        image_dirs[path] = {
                            "weight": weight,
                            "is_absolute": not is_percentage,
                        }
                    else:
                        specific_images[path] = {
                            "weight": weight,
                            "is_absolute": not is_percentage,
                        }
                elif os.path.isfile(line):
                    specific_images[line] = {"weight": 100, "is_absolute": False}

    return image_dirs, specific_images, ignored_dirs


def level(current_path):
    """Return:
    directory level of current_path where 1 is root of drive
    """

    return len([item for item in current_path.split(os.sep) if item != ""])


def folders_at_level(folder_list, level):
    """
    Return:
        Dictionary of folders at specified level
    """

    return [
        [folder, data] for folder, data in folder_list.items() if data["level"] == level
    ]


def build_folder_lists(image_dirs, ignored_dirs=None, scan_subfolders=True):
    """Recursively build directory of folders in image_dirs
    Ignore folders in ignored_dirs

    Returns:
        folder_data - dictionary of all folders to be included in slideshow
    """

    if ignored_dirs is None:
        ignored_dirs = []

    folder_data = defaultdict(lambda: {"level": 0, "weight": 100, "is_absolute": False})

    for path, data in image_dirs.items():
        for root, dirs, files in os.walk(path):
            if root in ignored_dirs:
                del dirs[:]
                continue

            images = [
                os.path.join(root, f)
                for f in files
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp"))
            ]
            if images:
                folder_data[root] = {
                    "level": level(root),
                    "weight": data["weight"],
                    "is_absolute": data["is_absolute"],
                }

            # Control whether to scan subfolders by modifying dirs in place
            if not scan_subfolders:
                del dirs[:]  # Clear dirs to prevent descending into subfolders

    # Remove empty folders
    # folder_image_paths = {k: v for k, v in folder_image_paths.items() if v}

    return folder_data


def calculate_weights(
    folder_data, specific_images, ignored_dirs, mode, depth, total_weight=1000000
):
    """
    Calculate weights of all images in folders in folders_data, and specified_images
    """

    all_image_paths = []
    weights_edit_list = {}

    weights = []

    def weigh_images(folder_tree, assigned_weight, weights_edit_list):

        sub_weights_edit_list = []
        virtual_folders = defaultdict(list)

        folder_index = list(folder_tree.keys())[0]
        folder_data = build_folder_lists(
            folder_tree, ignored_dirs, scan_subfolders=True
        )
        if folder_data:
            for path, data in folder_data.items():
                for root, dirs, files in os.walk(path, topdown=True):
                    images = [
                        os.path.join(root, f)
                        for f in files
                        if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp"))
                    ]
                    if images:
                        if level(path) < depth:
                            all_image_paths.extend(images)
                            if data["is_absolute"]:
                                sub_weights_edit_list.append(
                                    [(assigned_weight / data["weight"]), len(images)]
                                )
                            else:
                                sub_weights_edit_list.append(
                                    [
                                        (
                                            assigned_weight
                                            / len(images)
                                            * (data["weight"] / 100)
                                        ),
                                        len(images),
                                    ]
                                )
                        else:
                            vf = "\\".join(path.split("\\")[:depth])
                            for image in images:
                                virtual_folders[vf].append(image)
            for path, data in virtual_folders.items():
                all_image_paths.extend(data)
                sub_weights_edit_list.append([(assigned_weight / len(data)), len(data)])
            weights_edit_list[folder_index] = sub_weights_edit_list
        return weights_edit_list

    # Assign weights to image folders
    if mode[0] == "balanced":
        if mode[1] != 0:
            sub_folder_data = {}
            for path, data in folder_data.items():
                for root, dirs, files in os.walk(path, topdown=True):
                    current_level = level(root)
                    if current_level >= mode[1]:
                        sub_folder_data[root] = {
                            "level": current_level,
                            "weight": data["weight"],
                            "is_absolute": data["is_absolute"],
                        }
                        dirs[:] = []
            if not sub_folder_data:
                raise ValueError("No folders found at the requested level.")
                sys.exit()
            else:
                folder_data = sub_folder_data

        balanced_weight = total_weight / len(folder_data)
        for path, data in folder_data.items():
            weights_edit_list = weigh_images(
                {path: data}, balanced_weight, weights_edit_list
            )
    else:
        weights_edit_list = weigh_images(folder_data, total_weight, weights_edit_list)

    # # Handle virtual folders
    # if virtual_folders:
    #     for folder, images in virtual_folders.items():
    #         for image in images:
    #             all_image_paths.append(image)
    #         weights_edit_list[folder] = ([(total_weight / len(images)), len(images)])

    # Assign weights to specific images
    if specific_images:
        num_images = len(all_image_paths)
        num_folders = 0
        for path, data in weights_edit_list.items():
            num_folders += len(data)
        num_average_images = int(num_images / num_folders)
        for path, data in specific_images.items():
            is_percentage = not data["is_absolute"]
            all_image_paths.extend(
                [path] * (num_average_images if is_percentage else data["weight"])
            )
            weights_edit_list[path] = [
                (
                    [
                        (
                            total_weight
                            / (num_images if is_percentage else data["weight"])
                        ),
                        (num_average_images if is_percentage else data["weight"]),
                    ]
                )
            ]

    # Populate weights list
    for path, data in weights_edit_list.items():
        for weight_data in data:
            weights.extend([weight_data[0] / len(data)] * weight_data[1])
    return all_image_paths, weights


def test_distribution(
    image_paths, weights, iterations, mode, testdepth, is_random=False
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
            f"Directory: {directory}, Hits: {count}, Weight: {count / total_images * 1000000:.2f}"
        )


def main(
    input_files,
    test_iterations=None,
    mode=(),
    depth=None,
    testdepth=None,
    is_random=False,
    total_weight=1000000,
):

    start_time = time.time()

    image_dirs = defaultdict(lambda: {"weight": 100, "is_absolute": False, "depth": 0})
    specific_images = defaultdict(lambda: {"weight": 100, "is_absolute": False})
    ignored_dirs = []

    for input_filename in input_files:
        if os.path.isfile(input_filename):
            sub_image_dirs, sub_specific_images, sub_ignored_dirs = parse_input_file(
                input_filename
            )
            image_dirs.update(sub_image_dirs)
            specific_images.update(sub_specific_images)
            ignored_dirs.extend(sub_ignored_dirs)

    if not image_dirs and not specific_images:
        raise ValueError(
            "No images found in the provided directories and specific images."
        )
        sys.exit()
    all_image_paths, weights = calculate_weights(
        image_dirs, specific_images, ignored_dirs, mode, depth, total_weight
    )

    if test_iterations:
        test_distribution(
            all_image_paths, weights, test_iterations, mode, testdepth, is_random
        )
    else:
        root = tk.Tk()
        slideshow = ImageSlideshow(  # noqa: F841
            root, all_image_paths, weights, mode, is_random
        )  # noqa: F841
        root.mainloop()

    print("Finished --- %s seconds ---" % (time.time() - start_time))


if __name__ == "__main__":
    if args.run:
        input_files = args.input_file.split("+") if args.input_file else []
        main(
            input_files,
            mode=args.mode,
            depth=args.depth,
            is_random=args.random,
            total_weight=args.total_weight,
        )
    elif args.test:
        input_files = args.input_file.split("+") if args.input_file else []
        main(
            input_files,
            test_iterations=args.test,
            mode=args.mode,
            depth=args.depth,
            testdepth=args.testdepth if args.testdepth else args.depth + 1,
            is_random=args.random,
            total_weight=args.total_weight,
        )
