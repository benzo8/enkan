# ——— Standard library ———
import os
import sys
import random
import tkinter as tk
from tkinter import messagebox

# ——— Third-party ———
import vlc

# ——— Local ———
from slideshow import constants
from slideshow.cache.ImageCacheManager import ImageCacheManager
from slideshow.tree import Tree
from slideshow.tree.TreeNode import TreeNode
from slideshow.utils import utils
from slideshow.utils.Defaults import Defaults, resolve_mode
from slideshow.utils.Filters import Filters
from slideshow.utils.myStack import Stack
from slideshow.plugables.ImageProviders import ImageProviders
from slideshow.tree.tree_logic import (
    build_tree,
    extract_image_paths_and_weights_from_tree,
)
from .ZoomPan import ZoomPan

class ImageSlideshow:
    def __init__(
        self, 
        root: TreeNode, 
        tree: Tree, 
        image_paths: list, 
        cum_weights: list, 
        defaults: Defaults, 
        filters: Filters, 
        quiet: bool,
        interval: int | float | None = None
    ) -> None:
        self.root: TreeNode = root
        self.original_tree: Tree = tree
        self.image_paths: list = image_paths
        self.cum_weights: list = cum_weights
        self.original_cum_weights: list = cum_weights
        self.original_image_paths: list = image_paths
        self.number_of_images: int = len(image_paths)
        self.current_image_index = 0
        self.subFolderStack = Stack(1)
        self.parentFolderStack = Stack(constants.PARENT_STACK_MAX)
        self.subfolder_mode = False
        self.parent_mode = False
        self.navigation_mode = "folder"
        self.navigation_node = None
        self.show_filename = False

        self.screen_width: int = root.winfo_screenwidth()
        self.screen_height: int = root.winfo_screenheight()

        self.defaults: Defaults = defaults
        self.filters: Filters = filters
        self.video_muted: bool = self.defaults.mute
        self.quiet: bool = quiet
        self.interval: int | float | None = interval

        self.rotation_angle: int | float = 0

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

        # Zoom/Pan controller (binds mouse events on the label)
        self.zoompan = ZoomPan(self.label, self.screen_width, self.screen_height, on_image_changed=None)

        self.root.attributes("-fullscreen", True)
        self.root.bind("<space>", self.next_image)
        self.root.bind("<Escape>", self.exit_slideshow)

        for key in ["<Left>", "<Right>"]:
            self.root.bind(key, self.navigate_image_history)
        for key in ["<Up>", "<Down>"]:
            self.root.bind(key, self.navigate_image_sequential)
        for key in ["<c>", "<w>", "<l>", "<b>"]:
            self.root.bind(key, self.select_mode)

        self.root.bind("<Control-c>", lambda e: e.widget.event_generate("<<Copy>>"))

        self.root.bind("<t>", self.toggle_navigation_mode)
        self.root.bind("<u>", self.reset_parent_mode)
        self.root.bind("<o>", self.follow_branch_up)
        self.root.bind("<p>", self.follow_branch_down)
        self.root.bind("<i>", self.step_backwards)

        self.root.bind("<r>", self.rotate_image)
        self.root.bind("<Delete>", self.delete_image)

        self.root.bind("<m>", self.toggle_mute)
        self.root.bind("<n>", self.toggle_filename_display)
        self.root.bind("<s>", self.toggle_subfolder_mode)
        self.root.bind("<a>", self.toggle_auto_advance)

        # Zoom/Pan key bindings (avoid clashing with existing navigation)
        self.root.bind("=", lambda e: self.zoompan.zoom_in())  # '=' key (shift+'+' also triggers)
        self.root.bind("+", lambda e: self.zoompan.zoom_in())
        self.root.bind("-", lambda e: self.zoompan.zoom_out())
        self.root.bind("0", self._reset_zoom)
        # Shift + Arrows for panning so plain arrows keep history/sequential behaviour
        self.root.bind("<Shift-Left>", lambda e: self.zoompan.pan(-80, 0))
        self.root.bind("<Shift-Right>", lambda e: self.zoompan.pan(80, 0))
        self.root.bind("<Shift-Up>", lambda e: self.zoompan.pan(0, -80))
        self.root.bind("<Shift-Down>", lambda e: self.zoompan.pan(0, 80))

        self.providers = ImageProviders()
        if self.defaults.is_random:
            self.set_provider("random")
        else:
            self.set_provider("weighted", cum_weights=self.cum_weights)
        self.mode, _ = resolve_mode(self.defaults.mode, min(self.defaults.mode.keys()))

        self.show_image()
        if interval:
            self.auto_advance_interval = interval
            self._schedule_next_image()
            self.auto_advance_running = True

    def _reset_zoom(self, event=None) -> None:
        self.zoompan.reset_view()

    def update_slide_show(
        self, 
        image_paths: list, 
        cum_weights: list
    ) -> None:
        """Updates the slideshow with the new set of images and weights."""
        self.image_paths = image_paths
        self.cum_weights = cum_weights
        self.current_image_index = self.safe_current_image_index(image_paths)
        self.manager: ImageCacheManager = self.providers.reset_manager(
            image_paths=image_paths,
            provider_name=self.providers.get_current_provider_name(),
            cum_weights=self.cum_weights,
            index=self.current_image_index,
        )
        self.show_image(self.image_paths[self.current_image_index])

    def show_image(
        self, 
        image_path: str = None, 
        record_history: bool = True
    ) -> None:
        # Stop existing video playback and clean up resources
        if hasattr(self, "video_player") and self.video_player:
            self.video_player.stop()
            self.video_player.release()
            self.video_player = None
        if hasattr(self, "video_frame"):
            self.video_frame.place_forget()

        image_path, image = self.manager.get_next(
            image_path, record_history=record_history
        )

        self.current_image_path = image_path
        self.current_image_index = self.image_paths.index(image_path)

        if image:
            # If rotating, apply before handing to ZoomPan
            if hasattr(self, "rotation_angle") and self.rotation_angle:
                image = image.rotate(self.rotation_angle, expand=True)
            # Provide full-resolution image to ZoomPan, which will fit & manage viewport
            self.zoompan.set_image(image)
            self.label.pack()
        else:
            # Clear any existing image from label
            self.label.config(image="")
            self.label.image = None
            self.zoompan.orig_image = None  # disable zoom state while video plays
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
            self.root.after(500, self._check_video_ended)

        self.filename_label.tkraise()
        self.mode_label.tkraise()
        self.update_filename_display()

    def next_image(self, event=None) -> None:
        if self.rotation_angle != 0:
            self.rotation_angle = 0
        self.show_image()
        self.reset_auto_advance()

# --- Utility Methods ---

    def set_provider(
        self, 
        provider_name: str, 
        **provider_kwargs
    ) -> None:
        # Easily switch to any provider by name/key
        self.current_provider: str = provider_name
        self.manager: ImageCacheManager = self.providers.select_manager(
            image_paths=self.image_paths,
            provider_name=provider_name,
            debug=self.defaults.debug,
            background_preload=self.defaults.background,
            **provider_kwargs,
        )
        self.update_filename_display()

    def find_node_for_image(
        self, 
        image_path: str
    ) -> TreeNode:
        # First: specific image mapping
        node: TreeNode = self.original_tree.virtual_image_lookup.get(image_path)
        if node:
            return node
        # Fallback: directory-based
        return self.original_tree.find_node(os.path.dirname(image_path), self.original_tree.path_lookup)
    
    def safe_current_image_index(
        self, 
        image_paths: list
    ) -> int:
        number_of_images: int = len(image_paths)
        try:
            current_image_index: int = self.image_paths.index(self.current_image_path)
        except ValueError:
            current_image_index: int = random.randint(0, number_of_images - 1)

        return current_image_index

    def traverse_directory(self, new_path=None, navigation_node=None):
        """Set up for a new directory and create an updated slideshow."""
        if navigation_node:
            new_image_paths, new_weights = extract_image_paths_and_weights_from_tree(
                tree=self.original_tree, start_node=navigation_node
            )
        elif os.path.isdir(new_path):
            parent_image_dirs = {
                new_path: {
                    "weight_modifier": 100,
                    "is_percentage": True,
                    "proportion": None,
                }
            }
            parent_tree = build_tree(
                self.defaults, self.filters, parent_image_dirs, None, self.quiet
            )
            new_image_paths, new_weights = extract_image_paths_and_weights_from_tree(
                parent_tree
            )
        else:
            print("No valid directory found.")
        new_cum_weights = utils.prepare_cumulative_weights(new_weights)
        self.update_slide_show(new_image_paths, new_cum_weights)

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

# --- Auto Advance Methods ---

    def toggle_auto_advance(self, event=None, interval=None):
        """
        Toggle the automatic slideshow on/off.
        If enabling, optionally provide a new interval (ms).
        """
        if getattr(self, "auto_advance_running", False):
            if getattr(self, "auto_advance_id", None) is not None:
                self.root.after_cancel(self.auto_advance_id)
            self.auto_advance_id = None
            self.auto_advance_running = False
            print("[DEBUG] Auto-advance stopped.")
        else:
            if interval is not None:
                self.auto_advance_interval = interval
            if not hasattr(self, "auto_advance_interval"):
                self.auto_advance_interval = 5000
            self._schedule_next_image()
            self.auto_advance_running = True
            print(f"[DEBUG] Auto-advance started ({self.auto_advance_interval} ms).")

        self.update_filename_display()

    def _schedule_next_image(self):
        if getattr(self, "auto_advance_id", None) is not None:
            self.root.after_cancel(self.auto_advance_id)
        self.auto_advance_id = self.root.after(
            self.auto_advance_interval, self._advance_image
        )
        self.auto_advance_running = True

    def _advance_image(self):
        self.show_image()
        self._schedule_next_image()

    def reset_auto_advance(self):
        if getattr(self, "auto_advance_running", False):
            self._schedule_next_image()
    
# -- Keyboard Hooks ---

    def navigate_image_history(self, event=None):
        match event.keysym:
            case "Left":
                image_path, image_obj = self.manager.back()
            case "Right":
                image_path, image_obj = self.manager.forward()
        if image_path:
            if self.rotation_angle != 0:
                self.rotation_angle = 0
            self.show_image(image_path, record_history=False)
            self.reset_auto_advance()

    def navigate_image_sequential(self, event=None):
        match event.keysym:
            case "Up":
                image_path = self.image_paths[self.current_image_index + 1]
            case "Down":
                image_path = self.image_paths[self.current_image_index - 1]
        if self.rotation_angle != 0:
            self.rotation_angle = 0
        self.show_image(image_path)
        self.reset_auto_advance()

    def delete_image(self, event=None):
        if self.current_image_path:
            confirm = messagebox.askyesno(
                "Delete Image",
                f"Are you sure you want to delete {self.current_image_path}?",
            )
            if confirm:
                # Stop and release video player if a video is playing
                if hasattr(self, "video_player") and self.video_player:
                    self.video_player.stop()
                    self.video_player.release()
                    self.video_player = None
                if hasattr(self, "video_frame"):
                    self.video_frame.place_forget()
                try:
                    os.remove(self.current_image_path)
                    index = self.image_paths.index(self.current_image_path)
                    self.image_paths.pop(index)
                    self.cum_weights.pop(index)
                    self.manager.history_manager.remove(self.current_image_path)
                    self.update_slide_show(image_paths=self.image_paths, cum_weights=self.cum_weights)
                except Exception as e:
                    messagebox.showerror("Error", f"Could not delete the image: {e}")

    def toggle_mute(self, event=None):
        if hasattr(self, "video_player") and self.video_player:
            current_mute = self.video_player.audio_get_mute()
            new_mute = not current_mute
            self.video_player.audio_set_mute(new_mute)
            self.video_muted = new_mute

    def toggle_subfolder_mode(self, event=None):
        if not self.subfolder_mode:
            self.subfolder_mode_on()
        else:
            self.subfolder_mode_off()
        self.show_image(self.current_image_path)

    def toggle_navigation_mode(self, event=None):
        if self.navigation_mode == "branch":
            self.navigation_node = None
            self.navigation_mode = "folder"
        else:
            self.navigation_node = self.find_node_for_image(self.current_image_path)
            if self.navigation_node:
                self.navigation_mode = "branch"
            else:
                utils.log(
                    f"Cannot change mode - {self.current_image_path} not in tree",
                    self.defaults.debug,
                )
                return
        self.reset_parent_mode()
        self.update_filename_display()

    def subfolder_mode_on(self):
        folder = os.path.dirname(self.current_image_path)
        self.subFolderStack.push(folder, self.image_paths, self.cum_weights)

        temp_image_paths = [
            path for path in self.image_paths if path.startswith(folder)
        ]
        temp_weights = [1] * len(temp_image_paths)
        self.subfolder_mode = True
        temp_cum_weights = utils.prepare_cumulative_weights(temp_weights)
        self.update_slide_show(image_paths=temp_image_paths, cum_weights=temp_cum_weights)

    def subfolder_mode_off(self):
        _, self.image_paths, self.cum_weights = self.subFolderStack.pop()
        self.number_of_images = len(
            self.image_paths
        )
        self.subfolder_mode = False
        self.update_slide_show(image_paths=self.image_paths, weights=self.cum_weights)

    def select_mode(self, event=None):
        match event.char.upper():
            case "C":
                self.set_provider("random")
            case "L":
                self.set_provider("sequential", index=self.current_image_index + 1)
            case "W":
                self.set_provider("weighted", weights=self.cum_weights)
            case "B":
                self.set_provider("burst", weights=self.cum_weights, burst_size=5)

# -- Parent Mode Navigation ---

    def navigate_up(self):
        if self.parentFolderStack.is_full() or not self.parent_mode:
            print("Cannot navigate up - Stack is full or not in parent mode.")
            return

        current_path = os.path.dirname(self.current_image_path)
        current_top = self.parentFolderStack.read_top()
        child_path = None

        if self.navigation_mode == "folder":
            if utils.contains_subdirectory(current_top):
                current_path_level = utils.level_of(current_top)
                child_level = current_path_level + 1
                child_path = utils.truncate_path(current_path, child_level)

                if child_path == self.parentFolderStack.read_top(2):
                    self.step_backwards()
                    return
                elif not utils.contains_subdirectory(child_path):
                    self.toggle_subfolder_mode()
                else:
                    self.parentFolderStack.push(
                        child_path, self.image_paths, self.cum_weights
                    )
            else:
                print("No valid child directory found.")
        elif self.navigation_mode == "branch":
            current_path_node = self.original_tree.find_node(
                current_path, self.original_tree.path_lookup
            )
            path = []
            node = current_path_node
            while node and node != self.navigation_node:
                path.append(node)
                node = node.parent

            if node != self.navigation_node:
                print("No valid child node found in the branch.")
                return

            path.reverse()
            self.navigation_node = path[0] if path else self.navigation_node

        self.traverse_directory(child_path, self.navigation_node)

    def navigate_down(self):
        parent_path = None

        match (self.navigation_mode, self.parent_mode):
            case ("folder", False):
                current_path = os.path.dirname(self.current_image_path)
                current_path_level = utils.level_of(current_path)
                for i in range(current_path_level - 1, 1, -1):
                    parent_level = i
                    parent_path = utils.truncate_path(current_path, parent_level)
                    if utils.contains_subdirectory(
                        parent_path
                    ) > 1 or utils.contains_files(parent_path):
                        break
                self.parentFolderStack.push(parent_path, self.image_paths, self.cum_weights)
            case ("folder", True):
                previous_path = self.parentFolderStack.read_top()
                parent_level = utils.level_of(previous_path) - 1
                parent_path = utils.truncate_path(previous_path, parent_level)
                if parent_path == self.parentFolderStack.read_top(2):
                    self.step_backwards()
                    return
                self.parentFolderStack.push(parent_path, self.image_paths, self.cum_weights)
            case ("branch", False):
                self.navigation_node = self.find_node_for_image(self.current_image_path).parent
            case ("branch", True):
                self.navigation_node = self.navigation_node.parent

        self.parent_mode = True
        self.traverse_directory(parent_path, self.navigation_node)

    def step_backwards(self):
        if self.parentFolderStack.is_empty():
            print("Cannot step back - Stack is empty.")
            return
        _, images, cum_weights = self.parentFolderStack.pop()
        self.update_slide_show(images, cum_weights)

    def follow_branch_down(self, event=None):
        if self.subfolder_mode:
            self.toggle_subfolder_mode()
            return
        if self.parentFolderStack.is_full():
            print("Cannot navigate down - Stack is full.")
        else:
            self.navigate_down()

    def follow_branch_up(self, event=None):
        if self.subfolder_mode:
            self.subfolder_mode = False
            self.show_image(self.current_image_path)
            return
        self.navigate_up()

    def reset_parent_mode(self, event=None):
        self.parent_mode = False
        self.subfolder_mode = False
        self.parentFolderStack.clear()
        self.image_paths = self.original_image_paths[:]
        self.cum_weights = self.original_cum_weights[:]
        self.update_slide_show(self.image_paths, self.cum_weights)
        self.show_image(self.image_paths[self.current_image_index])
        print("[DEBUG] Parent mode reset and modes updated.")

# --- Filename and Mode Display Methods ---

    def toggle_filename_display(self, event=None):
        self.show_filename = not self.show_filename
        self.update_filename_display()

    def update_filename_display(self):
        if self.show_filename:
            fixed_colour = None
            fixed_path = None
            self.filename_label.config(state=tk.NORMAL)
            self.filename_label.delete("1.0", tk.END)
            label_path = self.current_image_path
            if self.navigation_mode == "branch":
                label_path = os.path.join(self.find_node_for_image(self.current_image_path).name, os.path.basename(self.current_image_path))
            match (self.navigation_mode, self.parent_mode, self.subfolder_mode):
                case ("folder", True, False):
                    fixed_path = self.parentFolderStack.read_top()
                    fixed_colour = "gold"
                case ("folder", _, True):
                    fixed_path = self.subFolderStack.read_top()
                    fixed_colour = "tomato"
                case ("branch", True, False):
                    fixed_path = self.navigation_node.name
                    fixed_colour = "lightgreen"
                case ("branch", _, True):
                    fixed_path = self.original_tree.find_node(
                        self.subFolderStack.read_top(), self.original_tree.path_lookup
                    ).name
                    fixed_colour = "tomato"

            if fixed_colour:
                if label_path.startswith(fixed_path):
                    fixed_portion = fixed_path
                    remaining_portion = label_path[len(fixed_path) :]
                else:
                    fixed_portion = ""
                    remaining_portion = label_path

                self.filename_label.insert(tk.END, fixed_portion, "fixed")
                self.filename_label.insert(tk.END, remaining_portion, "normal")
            else:
                self.filename_label.insert(tk.END, label_path, "normal")
                fixed_colour = "white"

            self.filename_label.tag_configure("fixed", foreground=fixed_colour)
            self.filename_label.tag_configure("normal", foreground="white")
            self.filename_label.place(x=0, y=0)
            self.filename_label.config(height=1, width=len(label_path) + 10, bg="black")
            self.filename_label.config(state=tk.DISABLED)

            mode_text = (
                self.providers.get_current_provider_name()[0:3].upper()
                if self.mode
                else "-"
            )
            if self.subfolder_mode:
                mode_text += " SUB"
                count = len(self.image_paths)
                idx = self.image_paths.index(self.current_image_path) + 1
                mode_text = f"({idx}/{count}) {mode_text}"
            elif self.parent_mode:
                mode_text += f" P{self.parentFolderStack.len()}"
                count = len(self.image_paths)
                idx = self.image_paths.index(self.current_image_path) + 1
                mode_text = f"({idx}/{count}) {mode_text}"
            else:
                mode_text = f"({self.current_image_index + 1}/{self.number_of_images}) {mode_text}"

            display_text = mode_text
            if (
                hasattr(self, "auto_advance_running")
                and self.auto_advance_running
                and hasattr(self, "auto_advance_interval")
                and self.auto_advance_interval > 0
            ):
                display_text = f"AUTO ({self.auto_advance_interval}ms)   {mode_text}"

            self.mode_label.config(
                text=display_text,
                fg="white",
            )
            self.mode_label.place(x=self.root.winfo_screenwidth(), y=0, anchor="ne")
        else:
            self.filename_label.place_forget()
            self.mode_label.place_forget()
        self.root.update_idletasks()

# --- Image Manipulation Methods ---

    def rotate_image(self, event=None):
        self.rotation_angle = (self.rotation_angle - 90) % 360
        self.show_image(self.current_image_path)

# --- Exit Method ---

    def exit_slideshow(self, event=None):
        self.manager.lru_cache.clear()
        self.manager.preload_queue.clear()
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
