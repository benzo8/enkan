# ——— Standard library ———
import os
import sys
import random
import tkinter as tk
from collections import deque
from tkinter import messagebox
from PIL import Image, ImageTk

# ——— Third-party ———
import vlc

# ——— Local ———
from slideshow import constants
from slideshow.utils import utils
from slideshow.utils.Defaults import resolve_mode
from slideshow.utils.MyStack import Stack
from slideshow.tree.Tree import Tree

class ImageSlideshow:
    def __init__(self, root, image_paths, weights, defaults):
        self.root = root
        self.image_paths = image_paths
        self.weights = weights
        self.original_image_paths = image_paths
        self.number_of_images = len(image_paths)
        self.current_image_index = 0
        self.original_weights = weights
        self.subFolderStack = Stack(1)
        self.parentFolderStack = Stack(constants.PARENT_STACK_MAX)
        self.history = deque(maxlen=constants.QUEUE_LENGTH_MAX)
        self.forward_history = deque(maxlen=constants.QUEUE_LENGTH_MAX)
        self.subfolder_mode = False
        self.parent_mode = False
        self.show_filename = False
        
        # Add preload queue
        self.preload_queue = deque(maxlen=3)
        self.preloaded_images = {}

        self.screen_width = root.winfo_screenwidth()
        self.screen_height = root.winfo_screenheight()

        self.defaults = defaults
        self.video_muted = self.defaults.mute
        
        self.initial_mode = self.defaults.mode
        if self.defaults.is_random:
            self.mode = "r"
        else:
            self.mode, _ = resolve_mode(self.defaults.mode, min(defaults.mode.keys()))

        self.rotation_angle = 0

        self.root.configure(background="black")  # Set root background to black
        self.label = tk.Label(root, bg="black")  # Set label background to black
        self.label.pack()

        self.filename_label = tk.Text(
            self.root,
            bg="black",
            fg="white",
            height=1,
            wrap="none",
            bd=0,
            highlightthickness=0,
        )
        self.filename_label.config(state=tk.DISABLED)
        self.mode_label = tk.Label(self.root, bg="black", fg="white", anchor="ne")

        self.root.attributes("-fullscreen", True)
        self.root.bind("<space>", self.next_image)
        self.root.bind("<Escape>", self.exit_slideshow)
        self.root.bind("<Left>", self.previous_image)
        self.root.bind("<Right>", self.next_image_forward)
        self.root.bind("<Delete>", self.delete_image)
        self.root.bind("<m>", self.toggle_mute)
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
        """
        Displays an image or plays a video in the slideshow application.

        If an image path is provided, displays the specified image or plays the specified video.
        If no image path is provided, selects the next image or video to display based on the current mode
        (random or weighted random selection). Handles updating the navigation history.

        For images:
            - Applies rotation if specified.
            - Resizes the image to fit the screen while maintaining aspect ratio.
            - Displays the image in the Tkinter label widget.

        For videos:
            - Stops any currently playing video.
            - Initializes and embeds a VLC media player instance into the Tkinter frame.
            - Plays the video and starts polling to detect when the video ends.

        Also updates filename and mode display labels.

        Args:
            image_path (str, optional): The file path of the image or video to display. If None, selects the next file automatically.

        Raises:
            RuntimeError: If the platform is unsupported for video playback embedding.
        """
        # Stop existing video playback and clean up resources
        if hasattr(self, "video_player") and self.video_player:
            self.video_player.stop()
            self.video_player.release()
            self.video_player = None
        if hasattr(self, "video_frame"):
            self.video_frame.place_forget()

        # If no specific path given and we have preloaded images, use one of those
        if image_path is None:
            if self.mode == "r":
                image_path = random.choice(self.image_paths)
            else:
                image_path = random.choices(
                    self.image_paths, weights=self.weights, k=1
                )[0]

            # Update history
            self.history.append(image_path)
            self.forward_history.clear()

        self.current_image_path = image_path
        self.current_image_index = self.image_paths.index(image_path)

        if utils.is_videofile(image_path):
            self.label.config(image="")
            self.label.image = None
            self.label.pack()

            if not hasattr(self, "video_frame"):
                self.video_frame = tk.Frame(self.root, bg="black")

            self.video_frame.place(
                x=0, y=0, width=self.screen_width, height=self.screen_height
            )

            if not hasattr(self, "vlc_instance"):
                self.vlc_instance = vlc.Instance("--no-video-title-show", "--quiet")

            media = self.vlc_instance.media_new(image_path)
            media.get_mrl()  # Ensure it's fully initialised

            self.video_player = self.vlc_instance.media_player_new()
            self.video_player.set_media(media)
            self.video_player.audio_set_mute(self.video_muted)

            # Embed into tkinter
            window_id = self.video_frame.winfo_id()
            if sys.platform.startswith("win"):
                self.video_player.set_hwnd(window_id)
            elif sys.platform.startswith("linux"):
                self.video_player.set_xwindow(window_id)
            elif sys.platform == "darwin":
                self.video_player.set_nsobject(window_id)
            else:
                raise RuntimeError(f"Unsupported platform: {sys.platform}")

            self.video_player.play()

            # Start polling to detect end of video
            self.root.after(500, self._check_video_ended)

        else:
            # Stop any video, hide video frame, and show image
            if hasattr(self, "video_frame"):
                self.video_frame.place_forget()

            # Load and process the image
            image = Image.open(image_path)
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

            # Apply rotation if needed (after getting image from either source)
            if self.rotation_angle != 0:
                image = image.rotate(self.rotation_angle, expand=True)

            # Convert to PhotoImage and display
            photo = ImageTk.PhotoImage(image)
            self.label.config(image=photo)
            self.label.image = photo
            self.label.pack()

        self.filename_label.tkraise()
        self.mode_label.tkraise()
        self.update_filename_display()

    def _check_video_ended(self):
        if not self.video_player:
            return

        length = self.video_player.get_length()
        time = self.video_player.get_time()

        if length > 0 and time >= length - 200:  # Account for buffering etc.
            self.video_player.stop()
            self.video_player.play()
            return

        self.root.after(500, self._check_video_ended)

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

    def toggle_mute(self, event=None):
        if hasattr(self, "video_player") and self.video_player:
            current_mute = self.video_player.audio_get_mute()
            new_mute = not current_mute
            self.video_player.audio_set_mute(new_mute)
            self.video_muted = new_mute  # Keep state in sync

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
        self.current_image_index = self.image_paths.index(self.current_image_path)
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
            current_path_level = utils.level_of(current_path)

            # Traverse up levels until a valid parent is found
            for i in range(current_path_level - 1, 1, -1):
                parent_level = i
                parent_path = utils.truncate_path(current_path, parent_level)
                if utils.contains_subdirectory(parent_path) > 1 or utils.contains_files(
                    parent_path
                ):
                    break

            self.parentFolderStack.push(
                parent_path, self.original_image_paths, self.original_weights
            )
        else:  # Handle moving up a level in parent mode (S3)
            previous_path = self.parentFolderStack.read_top()
            parent_level = utils.level_of(previous_path) - 1
            parent_path = utils.truncate_path(previous_path, parent_level)

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
                    "depth": self.defaults.depth,
                }
            }

            # Build the new tree and extract images and weights
            parent_tree.build_tree(parent_image_dirs, None, self.defaults)
            parent_tree.calculate_weights()
            self.image_paths, self.weights = (
                parent_tree.extract_image_paths_and_weights_from_tree()
            )

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
        if (
            self.parentFolderStack.is_full() or not self.parent_mode
        ):  # Test for S0 or trying to move up when not in parent_mode
            print("S0 - Doing nothing")
            return

        if self.subfolder_mode and not self.parentFolderStack.is_empty():  # S4
            self.subfolder_mode_off()
            self.show_image(self.current_image_path)
            self.update_filename_display()
            return

        # if not self.parent_mode: # S2
        current_path = os.path.dirname(self.current_image_path)
        current_top = self.parentFolderStack.read_top()
        if utils.contains_subdirectory(current_top):
            current_path_level = utils.level_of(current_top)
            parent_level = current_path_level + 1
            parent_path = utils.truncate_path(current_path, parent_level)

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

                parent_tree = Tree()
                parent_image_dirs[parent_path] = {
                    "weight_modifier": 100,
                    "is_percentage": True,
                    "proportion": None,
                    "mode_str": self.defaults.mode[1],
                    "depth": self.defaults.depth,
                }
                parent_tree.build_tree(parent_image_dirs, None, self.defaults)
                parent_tree.calculate_weights()
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
            self.image_paths, self.weights = (
                self.original_image_paths,
                self.original_weights,
            )
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
                fixed_colour = "tomato"
            elif self.parent_mode:
                fixed_path = (
                    self.parentFolderStack.read_top()
                )  # The "fixed" portion of the path
                fixed_colour = "gold"
            if fixed_colour:
                if self.current_image_path.startswith(fixed_path):
                    fixed_portion = fixed_path
                    remaining_portion = self.current_image_path[len(fixed_path) :]
                else:
                    fixed_portion = ""
                    remaining_portion = self.current_image_path

                self.filename_label.insert(tk.END, fixed_portion, "fixed")
                self.filename_label.insert(tk.END, remaining_portion, "normal")
            else:
                # In normal mode, the entire filename is in white
                self.filename_label.insert(tk.END, self.current_image_path, "normal")
                fixed_colour = "white"

            # Apply the tags for coloring
            self.filename_label.tag_configure("fixed", foreground=fixed_colour)
            self.filename_label.tag_configure("normal", foreground="white")

            # Set the filename label position
            self.filename_label.place(x=0, y=0)
            self.filename_label.config(
                height=1, width=len(self.current_image_path) + 10, bg="black"
            )

            # Disable the text widget to prevent editing
            self.filename_label.config(state=tk.DISABLED)

            mode_text = self.mode.upper() if self.mode else "-"
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
        if self.mode == "r":
            self.mode = self.initial_mode
        else:
            self.mode = "r"
        self.update_filename_display()

    def rotate_image(self, event=None):
        self.rotation_angle = (self.rotation_angle - 90) % 360
        self.show_image(self.current_image_path)

    def exit_slideshow(self, event=None):
        # Clear preloaded images
        self.preloaded_images.clear()
        self.preload_queue.clear()
        if hasattr(self, "video_player") and self.video_player:
            self.video_player.stop()
            self.video_player.release()
            self.video_player = None
        if hasattr(self, "vlc_instance") and self.vlc_instance:
            self.vlc_instance.release()
            self.vlc_instance = None
        if hasattr(self, "video_frame"):
            self.video_frame.destroy()
        self.root.destroy()

