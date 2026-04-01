# ——— Standard library ———
import os
import sys
import tkinter as tk
import logging
from dataclasses import dataclass, field
from typing import Optional

# ——— Third-party ———
import vlc

# ——— Local ———
from enkan import constants
from enkan.cache.CachedVideoData import CachedVideoData
from enkan.cache.ImageCacheManager import ImageCacheManager
from enkan.tree import Tree
from enkan.tree.TreeNode import TreeNode
from enkan.utils import utils
from enkan.utils.Defaults import Defaults, resolve_mode, parse_mode_string
from enkan.plugables.FolderSelectionMemory import FolderSelectionMemory
from enkan.utils.Filters import Filters
from enkan.utils.SelectionWeights import SelectionWeights
from enkan.plugables.ImageProviders import ImageProviders
from enkan.tree.tree_logic import (
    apply_mode_and_recalculate,
    build_tree,
    extract_image_paths_and_weights_from_tree,
)
from enkan.tree.diagnostics import print_tree
from enkan.mySlideshow.Gui.Gui import Gui
from enkan.mySlideshow.MediaFileOps import (
    ORIENTATION_TO_CW,
    delete_media_file,
    write_exif_orientation,
)
from enkan.mySlideshow.ScopeStack import ScopeStack, ScopeStackEntry
from enkan.mySlideshow.ZoomPan import ZoomPan

# Configure logging
logger: logging.Logger = logging.getLogger("enkan.ui")

CRW_DISPLAY_MODES = ("off", "friendly", "useful", "debug")


@dataclass
class _ScopeState:
    selection_weights: SelectionWeights
    folder_memory: FolderSelectionMemory
    seen_folders: set[str] = field(default_factory=set)


class ImageSlideshow:
    def __init__(
        self,
        root: TreeNode,
        tree: Tree,
        image_paths: list,
        selection_weights: SelectionWeights,
        defaults: Defaults,
        filters: Filters,
        interval: int | float | None = None,
    ) -> None:
        self.root: TreeNode = root
        self.original_tree: Tree = tree
        self.image_paths: list = image_paths
        self.selection_weights: SelectionWeights = selection_weights.copy()
        self.original_selection_weights: SelectionWeights = selection_weights.copy()
        self.folder_memory: FolderSelectionMemory = self._new_scope_memory()
        self.original_folder_memory: FolderSelectionMemory = self.folder_memory.copy()
        self.scope_seen_folders: set[str] = set()
        self.original_scope_seen_folders: set[str] = set()
        self.original_image_paths: list = image_paths
        self.number_of_images: int = len(image_paths)
        self.current_image_index = 0
        self.subFolderStack: ScopeStack[_ScopeState] = ScopeStack(1)
        self.parentFolderStack: ScopeStack[_ScopeState] = ScopeStack(
            constants.PARENT_STACK_MAX
        )
        self.subfolder_mode = False
        self.parent_mode = False
        self.navigation_mode = "folder"
        self.navigation_node = None
        self.show_filename = False
        self._last_burst_memory_token = None
        self.crw_display_mode_index = 0
        self.current_crw_metrics = None
        self.folder_base_totals: dict[str, float] = {}
        self.one_folder_only = False
        self.controlled_random_settings = {
            "gap_min": 3,
            "gap_max": 80,
            "alpha": 0.01,
            "repeat_penalty": 0.1,
        }

        self.screen_width: int = root.winfo_screenwidth()
        self.screen_height: int = root.winfo_screenheight()

        self.defaults: Defaults = defaults
        self.filters: Filters = filters
        self.video_muted: bool = self.defaults.mute
        self.interval: int | float | None = interval

        self.rotation_angle: int | float = 0
        self.current_exif_orientation: int = 1
        self.current_vlc_media = None
        self.current_video_payload: CachedVideoData | None = None

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
        self.mode_dialog: object | None = None
        self._ignore_user_proportion: bool = False

        # Zoom/Pan controller (binds mouse events on the label)
        self.zoompan = ZoomPan(
            self.label,
            self.screen_width,
            self.screen_height,
            on_image_changed=self.update_filename_display,
        )

        self.root.attributes("-fullscreen", True)
        self.root.bind("<space>", self.next_image)
        self.root.bind("<Escape>", self.exit_slideshow)

        for key in ["<Left>", "<Right>"]:
            self.root.bind(key, self.navigate_image_history)
        for key in ["<Up>", "<Down>"]:
            self.root.bind(key, self.navigate_image_sequential)
        for key in ["<c>", "<w>", "<l>", "<b>", "<d>"]:
            self.root.bind(key, self.select_mode)

        self.root.bind("<Control-c>", lambda e: e.widget.event_generate("<<Copy>>"))

        self.root.bind("<t>", self.toggle_navigation_mode)
        self.root.bind("<u>", self.reset_parent_mode)
        self.root.bind("<o>", self.follow_branch_up)
        self.root.bind("<p>", self.follow_branch_down)
        self.root.bind("<i>", self.step_backwards)

        self.root.bind("<r>", self.rotate_image)
        self.root.bind("<Control-r>", self.persist_rotation_to_exif)
        self.root.bind("<Delete>", self.delete_image)

        self.root.bind("<m>", self.toggle_mute)
        self.root.bind("<n>", self.toggle_filename_display)
        self.root.bind("<s>", self.toggle_subfolder_mode)
        self.root.bind("<Control-b>", self.reset_burst_cycle)
        self.root.bind("<Control-d>", self.clear_memory)
        self.root.bind("<D>", self.toggle_crw_display_mode)
        self.root.bind("<a>", self.toggle_auto_advance)
        self.root.bind("<Control-Shift-M>", self.open_mode_dialog)
        self.root.bind("<Control-Shift-T>", self.print_tree_to_console)

        # Zoom/Pan key bindings (avoid clashing with existing navigation)
        self.root.bind(
            "=", lambda e: self.zoompan.zoom_in()
        )  # '=' key (shift+'+' also triggers)
        self.root.bind("+", lambda e: self.zoompan.zoom_in())
        self.root.bind("-", lambda e: self.zoompan.zoom_out())
        self.root.bind("0", self._reset_zoom)
        # Shift + Arrows for panning so plain arrows keep history/sequential behaviour
        self.root.bind("<Shift-Left>", lambda e: self.zoompan.pan(-80, 0))
        self.root.bind("<Shift-Right>", lambda e: self.zoompan.pan(80, 0))
        self.root.bind("<Shift-Up>", lambda e: self.zoompan.pan(0, -80))
        self.root.bind("<Shift-Down>", lambda e: self.zoompan.pan(0, 80))

        # Instantiate Classes
        self.gui = Gui(use_customtkinter=True)
        self.providers = ImageProviders()
        self._rebuild_folder_weight_cache()
        self._recalculate_controlled_random_settings()
        
        if self.defaults.is_random:
            self.set_provider("random")
        else:
            self.set_provider("weighted")
        self.mode, _ = resolve_mode(self.defaults.mode, min(self.defaults.mode.keys()))

        self.show_image()
        if interval:
            self.auto_advance_interval: int | float = interval
            self._schedule_next_image()
            self.auto_advance_running = True

    def _reset_zoom(self, event=None) -> None:
        self.zoompan.reset_view()

    def _new_scope_memory(self) -> FolderSelectionMemory:
        return FolderSelectionMemory()

    def _release_video_resources(self) -> None:
        if hasattr(self, "video_player") and self.video_player:
            self.video_player.stop()
            self.video_player.release()
            self.video_player = None
        if self.current_vlc_media is not None:
            try:
                self.current_vlc_media.release()
            except Exception:
                logger.debug("Failed to release VLC media cleanly.", exc_info=True)
            self.current_vlc_media = None
        self.current_video_payload = None

    def _capture_scope_state(self) -> _ScopeState:
        return _ScopeState(
            selection_weights=self.selection_weights.copy(),
            folder_memory=self.folder_memory.copy(),
            seen_folders=set(self.scope_seen_folders),
        )

    def _apply_scope_state(self, scope_state: _ScopeState) -> None:
        self.selection_weights = scope_state.selection_weights.copy()
        self.folder_memory = scope_state.folder_memory.copy()
        self.scope_seen_folders = set(scope_state.seen_folders)
        self._last_burst_memory_token = None

    def _sync_original_scope_state(self) -> None:
        if self.parent_mode or self.subfolder_mode:
            return
        self.original_image_paths = self.image_paths[:]
        self.original_selection_weights = self.selection_weights.copy()
        self.original_folder_memory = self.folder_memory.copy()
        self.original_scope_seen_folders = set(self.scope_seen_folders)

    def _scope_records_once_per_folder(self) -> bool:
        return self.subfolder_mode or self.parent_mode

    def _record_scope_entry(self, folder: str) -> None:
        if not folder:
            return
        self.folder_memory.record_folder(folder)
        self._sync_original_scope_state()

    def _crw_folder_metrics_for_path(self, image_path: str) -> dict[str, float | int | str] | None:
        if self.providers.get_current_provider_name() != "controlled_random_weighted":
            return None
        folder = os.path.dirname(image_path)
        if not folder:
            return None
        return self._crw_folder_metrics(folder=folder)

    def _record_memory_for_view(self, image_path: str, record_history: bool) -> None:
        if not record_history:
            return

        provider_name = self.providers.get_current_provider_name()
        if provider_name == "sequential":
            return

        folder = os.path.dirname(image_path)
        if not folder:
            return

        if provider_name == "burst":
            burst_token = getattr(self.manager.image_provider, "current_burst_token", None)
            if burst_token is not None and burst_token == self._last_burst_memory_token:
                return
            self._last_burst_memory_token = burst_token
            burst_folder = getattr(self.manager.image_provider, "current_burst_folder", None)
            self.folder_memory.record_folder(burst_folder or folder)
            self._sync_original_scope_state()
            return

        if self._scope_records_once_per_folder():
            if folder in self.scope_seen_folders:
                return
            self.scope_seen_folders.add(folder)

        self.folder_memory.record_folder(folder)
        self._sync_original_scope_state()

    def show_image(self, image_path: str = None, record_history: bool = True) -> None:
        # Stop existing video playback and clean up resources
        self._release_video_resources()
        if hasattr(self, "video_frame"):
            self.video_frame.place_forget()

        image_path, media_payload = self.manager.get_next(
            image_path, record_history=record_history
        )
        if not image_path:
            logger.warning("No displayable media available.")
            return

        self.current_image_path: str = image_path
        self.current_image_index = self.image_paths.index(image_path)
        if (
            self.providers.get_current_provider_name() == "controlled_random_weighted"
            and self._current_crw_display_mode() != "off"
        ):
            self.current_crw_metrics = self._crw_folder_metrics_for_path(image_path)
        else:
            self.current_crw_metrics = None
        self._record_memory_for_view(image_path, record_history)

        if not utils.is_videofile(image_path):
            image = media_payload
            self.current_vlc_media = None
            self.current_video_payload = None
            self.current_exif_orientation = image.info.get("exif_orientation", 1)
            # If rotating, apply before handing to ZoomPan
            if hasattr(self, "rotation_angle") and self.rotation_angle:
                image = image.rotate(self.rotation_angle, expand=True)
            # Provide full-resolution image to ZoomPan, which will fit & manage viewport
            self.zoompan.set_image(image)
            self.label.pack()
        else:
            self.current_exif_orientation = 1
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

            media = None
            if isinstance(media_payload, CachedVideoData):
                media = media_payload.to_vlc_media(self.vlc_instance)
            if media is None:
                logger.debug("Falling back to path-based VLC media for %s", image_path)
                media = self.vlc_instance.media_new(image_path)
                media.get_mrl()  # Ensure it's fully initialised

            self.video_player = self.vlc_instance.media_player_new()
            self.video_player.set_media(media)
            self.video_player.audio_set_mute(self.video_muted)
            self.current_vlc_media = media
            self.current_video_payload = (
                media_payload if isinstance(media_payload, CachedVideoData) else None
            )

            window_id: int = self.video_frame.winfo_id()
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

    def _provider_kwargs(self) -> dict[str, object]:
        return {
            **self.selection_weights.provider_kwargs(),
            "folder_memory": self.folder_memory,
        }

    def _rebuild_folder_weight_cache(self) -> None:
        folder_base_totals: dict[str, float] = {}
        for path, weight in zip(self.image_paths, self.selection_weights.weights):
            folder = os.path.dirname(path)
            if not folder:
                continue
            folder_base_totals[folder] = folder_base_totals.get(folder, 0.0) + weight
        self.folder_base_totals = folder_base_totals
        self.one_folder_only = len(folder_base_totals) <= 1

    def _controlled_random_folder_count(self) -> int:
        return max(1, len(self.folder_base_totals))

    def _recalculate_controlled_random_settings(self) -> None:
        folder_count = self._controlled_random_folder_count()
        gap_min = max(1, int(self.controlled_random_settings["gap_min"]))
        gap_max = max(gap_min + 1, min(80, round(folder_count * 1.5)))
        alpha = max(0.0025, min(0.03, 0.12 / folder_count))
        self.controlled_random_settings["gap_max"] = gap_max
        self.controlled_random_settings["alpha"] = alpha

    def _provider_display_name(self) -> str:
        provider_name = self.providers.get_current_provider_name()
        labels = {
            "random": "RND",
            "weighted": "WGT",
            "controlled_random_weighted": "CRW",
            "sequential": "SEQ",
            "burst": "BUR",
        }
        return labels.get(provider_name, provider_name[0:3].upper())

    def _current_crw_display_mode(self) -> str:
        return CRW_DISPLAY_MODES[self.crw_display_mode_index]

    def _crw_folder_metrics(self, folder: str | None = None) -> dict[str, float | int | str] | None:
        if self.providers.get_current_provider_name() != "controlled_random_weighted":
            return None
        if folder is None:
            if not self.current_image_path:
                return None
            folder = os.path.dirname(self.current_image_path)
        if not folder or not self.image_paths:
            return None

        seen_before = self.folder_memory.has_seen(folder)
        distance = self.folder_memory.distance_for(folder)
        gap_min = max(0, int(self.controlled_random_settings["gap_min"]))
        gap_max = max(gap_min, int(self.controlled_random_settings["gap_max"]))
        alpha = float(self.controlled_random_settings["alpha"])
        repeat_penalty = max(
            0.0,
            min(float(self.controlled_random_settings["repeat_penalty"]), 1.0),
        )
        if not seen_before:
            distance = min(distance, gap_max)
        clamped_distance = min(distance, gap_max)
        one_folder_only = self.one_folder_only
        streak_len = self.folder_memory.streak_for(folder)

        if one_folder_only:
            folder_factor = 1.0
        elif gap_min > 0 and distance < gap_min:
            folder_factor = repeat_penalty + (
                (1.0 - repeat_penalty) * (distance / gap_min)
            )
        else:
            folder_factor = 1.0

        extra = max(0.0, clamped_distance - 10)
        boost = 1.0 + alpha * extra * extra
        if one_folder_only or not seen_before or streak_len <= 0:
            streak_factor = 1.0
        else:
            streak_factor = max(0.25, 0.75 ** max(0, streak_len - 1))
        combined = folder_factor * boost * streak_factor

        base_total = self.folder_base_totals.get(folder, 0.0)
        effective_total = base_total * combined

        bias_pct = ((combined - 1.0) * 100.0) if base_total > 0 else 0.0
        return {
            "folder": folder,
            "age": distance,
            "seen_before": seen_before,
            "streak_len": streak_len,
            "folder_factor": folder_factor,
            "boost": boost,
            "streak_factor": streak_factor,
            "combined": combined,
            "bias_pct": bias_pct,
            "base_total": base_total,
            "effective_total": effective_total,
        }

    def _crw_status_text(self) -> str:
        mode = self._current_crw_display_mode()
        if mode == "off":
            return ""

        metrics = self.current_crw_metrics or self._crw_folder_metrics()
        if metrics is None:
            return ""

        age = int(metrics["age"])
        seen_before = bool(metrics["seen_before"])
        streak_len = int(metrics["streak_len"])
        bias_pct = float(metrics["bias_pct"])
        folder_factor = float(metrics["folder_factor"])
        boost = float(metrics["boost"])
        streak_factor = float(metrics["streak_factor"])
        combined = float(metrics["combined"])

        if mode == "friendly":
            if not seen_before:
                return "NEW"
            if combined >= 1.75:
                label = "DUE"
            elif combined >= 1.15:
                label = "WARM"
            elif folder_factor < 0.75:
                label = "COOLING"
            else:
                label = "NEUTRAL"
            return label

        if mode == "useful":
            if not seen_before:
                return f"NEW S{streak_len} B{bias_pct:+.0f}%"
            return f"A{age} S{streak_len} B{bias_pct:+.0f}%"

        if not seen_before:
            return (
                f"NEW S{streak_len} F{folder_factor:.2f} U{boost:.2f} T{streak_factor:.2f} "
                f"X{combined:.2f} B{bias_pct:+.0f}%"
            )
        return (
            f"A{age} S{streak_len} F{folder_factor:.2f} U{boost:.2f} T{streak_factor:.2f} "
            f"X{combined:.2f} B{bias_pct:+.0f}%"
        )

    def update_slide_show(
        self,
        image_paths: list,
        selection_weights: SelectionWeights,
        record_initial_history: bool = False,
        preferred_index: int | None = None,
    ) -> None:
        """Updates the slideshow with the new set of images and weights."""
        history_snapshot = (
            self.manager.history_snapshot() if getattr(self, "manager", None) else None
        )
        self.image_paths = image_paths
        self.selection_weights = selection_weights.copy()
        self._rebuild_folder_weight_cache()
        self._recalculate_controlled_random_settings()
        self.number_of_images = len(image_paths)
        self.current_image_index = self.safe_current_image_index(
            image_paths,
            preferred_index=preferred_index,
        )
        if not image_paths:
            self.current_image_path = None
            self.update_filename_display()
            return
        self.manager: ImageCacheManager = self.providers.reset_manager(
            image_paths=image_paths,
            provider_name=self.providers.get_current_provider_name(),
            index=self.current_image_index,
            **self._provider_kwargs(),
        )
        self.manager.restore_history(history_snapshot)
        self._last_burst_memory_token = None
        self.show_image(
            self.image_paths[self.current_image_index],
            record_history=record_initial_history,
        )

    # --- Utility Methods ---

    def _check_video_ended(self) -> None:
        if not self.video_player:
            return

        length = self.video_player.get_length()
        time = self.video_player.get_time()

        if length > 0 and time >= length - 200:  # Account for buffering etc.
            self.video_player.stop()
            self.video_player.play()
            return

        self.root.after(500, self._check_video_ended)

        # --- Dynamic mode adjustment ---

    def set_provider(self, provider_name: str, **provider_kwargs) -> None:
        # Easily switch to any provider by name/key
        self.current_provider: str = provider_name
        history_snapshot = (
            self.manager.history_snapshot() if getattr(self, "manager", None) else None
        )
        if provider_name == "controlled_random_weighted":
            self._recalculate_controlled_random_settings()
            for key in self.controlled_random_settings:
                if key in provider_kwargs:
                    self.controlled_random_settings[key] = provider_kwargs[key]
        provider_kwargs = {
            **self._provider_kwargs(),
            **provider_kwargs,
        }
        provider_kwargs.setdefault("index", self.current_image_index)
        self.manager: ImageCacheManager = self.providers.select_manager(
            image_paths=self.image_paths,
            provider_name=provider_name,
            background_preload=self.defaults.background,
            **provider_kwargs,
        )
        self.manager.restore_history(history_snapshot)
        self._last_burst_memory_token = None
        self.update_filename_display()

    def toggle_crw_display_mode(self, event=None) -> None:
        self.crw_display_mode_index = (
            self.crw_display_mode_index + 1
        ) % len(CRW_DISPLAY_MODES)
        logger.debug(
            "Controlled-random display mode set to %s.",
            self._current_crw_display_mode(),
        )
        self.update_filename_display()

    def find_node_for_image(self, image_path: str) -> TreeNode:
        # First: specific image mapping
        node: TreeNode = self.original_tree.virtual_image_lookup.get(image_path)
        if node:
            return node
        # Fallback: directory-based
        return self.original_tree.find_node(
            os.path.dirname(image_path), self.original_tree.path_lookup
        )

    def safe_current_image_index(
        self,
        image_paths: list,
        preferred_index: int | None = None,
    ) -> int:
        number_of_images: int = len(image_paths)
        if number_of_images <= 0:
            return 0

        if self.current_image_path in image_paths:
            return image_paths.index(self.current_image_path)

        if preferred_index is None:
            preferred_index = getattr(self, "current_image_index", 0)

        if preferred_index is None:
            return 0

        return max(0, min(int(preferred_index), number_of_images - 1))

    def traverse_directory(
        self,
        new_path=None,
        navigation_node=None,
        record_initial_history: bool = False,
    ) -> None:
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
            parent_tree: Tree.Tree = build_tree(
                self.defaults,
                self.filters,
                parent_image_dirs,
                None,
                tk_root=self.root,
                tk_enabled=True,
            )
            new_image_paths, new_weights = extract_image_paths_and_weights_from_tree(
                parent_tree
            )
        else:
            logger.debug("No valid directory found.")
        self.update_slide_show(
            new_image_paths,
            SelectionWeights.from_weights(new_weights),
            record_initial_history=record_initial_history,
        )

    # --- Dynamic Mode Methods ---

    def _handle_mode_apply(self, mode_str: str, ignore_user: bool) -> Optional[str]:
        mode_dict = parse_mode_string(mode_str)
        if not mode_dict:
            raise ValueError("Unable to parse mode string.")
        self._ignore_user_proportion = ignore_user
        self.defaults.set_global_defaults(mode=mode_dict)
        self._recalculate_slideshow(ignore_user=ignore_user)
        return self.original_tree.current_mode_string() or mode_str

    def _handle_mode_reset(self) -> Optional[str]:
        if not self.original_tree.built_mode:
            raise ValueError("Tree does not have a recorded original mode.")
        return (
            self.original_tree.built_mode_string
            or self.original_tree.current_mode_string()
        )

    def _recalculate_slideshow(self, ignore_user: bool) -> None:
        images, weights, cum_weights = apply_mode_and_recalculate(
            self.original_tree, self.defaults, ignore_user_proportion=ignore_user
        )
        self.original_image_paths = images[:]
        self.folder_memory = self._new_scope_memory()
        self.scope_seen_folders = set()
        self.original_selection_weights = SelectionWeights.from_parts(
            weights,
            cum_weights,
        )
        self.original_folder_memory = self.folder_memory.copy()
        self.original_scope_seen_folders = set()
        self.update_slide_show(
            images,
            SelectionWeights.from_parts(weights, cum_weights),
        )
        mode_dict = self.defaults.mode or {}
        if mode_dict:
            lowest = min(mode_dict.keys())
            self.mode, _ = resolve_mode(mode_dict, lowest)
        else:
            self.mode = None
        self.update_filename_display()

    def _on_dialog_closed(self, _event=None) -> None:
        self.mode_dialog = None

    def open_mode_dialog(self, event=None) -> None:
        if self.mode_dialog:
            try:
                self.mode_dialog.top.lift()
                return
            except tk.TclError:
                self.mode_dialog = None

        current_mode = self.original_tree.current_mode_string() or ""
        dialog = self.gui.create_mode_adjust_dialog(
            parent=self.root,
            current_mode=current_mode,
            on_apply=self._handle_mode_apply,
            on_reset=self._handle_mode_reset,
            ignore_default=self._ignore_user_proportion,
        )
        dialog.top.bind("<Destroy>", self._on_dialog_closed)
        self.mode_dialog = dialog

    # --- Auto Advance Methods ---

    def _schedule_next_image(self) -> None:
        if getattr(self, "auto_advance_id", None) is not None:
            self.root.after_cancel(self.auto_advance_id)
        self.auto_advance_id = self.root.after(
            self.auto_advance_interval, self._advance_image
        )
        self.auto_advance_running = True

    def _advance_image(self) -> None:
        self.show_image()
        self._schedule_next_image()

    def toggle_auto_advance(self, event=None, interval=None) -> None:
        """
        Toggle the automatic slideshow on/off.
        If enabling, optionally provide a new interval (ms).
        """
        if getattr(self, "auto_advance_running", False):
            if getattr(self, "auto_advance_id", None) is not None:
                self.root.after_cancel(self.auto_advance_id)
            self.auto_advance_id = None
            self.auto_advance_running = False
            logger.debug("Auto-advance stopped.")
        else:
            if interval is not None:
                self.auto_advance_interval = interval
            if not hasattr(self, "auto_advance_interval"):
                self.auto_advance_interval = 5000
            self._schedule_next_image()
            self.auto_advance_running = True
            logger.debug("Auto-advance started (%s ms).", self.auto_advance_interval)

        self.update_filename_display()

    def reset_auto_advance(self) -> None:
        if getattr(self, "auto_advance_running", False):
            self._schedule_next_image()

    # -- Keyboard Hooks ---

    def _confirm_action(self, title: str, message: str) -> bool:
        return bool(self.gui.messagebox(title=title, message=message, type_="yesno"))

    def _show_error(self, title: str, message: str) -> None:
        self.gui.messagebox(title, message, icon="error")

    def _show_warning(self, title: str, message: str) -> None:
        self.gui.messagebox(title, message, icon="warning")

    def delete_image(self, event=None) -> None:
        if self.current_image_path:
            confirm: bool = self._confirm_action(
                "Delete Image",
                f"Are you sure you want to delete {self.current_image_path}?",
            )
            if confirm:
                # Stop and release video player if a video is playing
                self._release_video_resources()
                if hasattr(self, "video_frame"):
                    self.video_frame.place_forget()
                try:
                    deleted_path = self.current_image_path
                    delete_media_file(deleted_path)
                    index = self.image_paths.index(deleted_path)
                    self.image_paths.pop(index)
                    self.selection_weights.remove_at(index)
                    self.manager.history_manager.remove(deleted_path)
                    if not self.image_paths:
                        self.current_image_path = None
                        self.current_image_index = 0
                        self._sync_original_scope_state()
                        self.exit_slideshow()
                        return
                    next_index = min(index, len(self.image_paths) - 1)
                    self.current_image_index = next_index
                    self.current_image_path = self.image_paths[next_index]
                    self.update_slide_show(
                        image_paths=self.image_paths,
                        selection_weights=self.selection_weights,
                        preferred_index=next_index,
                    )
                    self._sync_original_scope_state()
                except Exception as e:
                    self._show_error("Error", f"Could not delete the image: {e}")

    def navigate_image_history(self, event=None) -> None:
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

    def navigate_image_sequential(self, event=None) -> None:
        try:
            match event.keysym:
                case "Up":
                    image_path = self.image_paths[self.current_image_index + 1]
                case "Down":
                    image_path = self.image_paths[self.current_image_index - 1]
            if self.rotation_angle != 0:
                self.rotation_angle = 0
            self.show_image(image_path)
            self.reset_auto_advance()
        except IndexError:
            logger.debug(
                "navigate_image_sequential: Index out of range for image_paths."
            )

    def persist_rotation_to_exif(self, event=None) -> None:
        if not self.current_image_path or not utils.is_imagefile(
                    self.current_image_path
        ):
            return
        if utils.is_videofile(self.current_image_path):
            return
        if self.rotation_angle % 360 == 0:
            return

        confirm: bool = self._confirm_action(
            "Update Rotation",
            "Apply the current rotation to this image's EXIF orientation?",
        )
        if not confirm:
            return
        try:
            outcome = write_exif_orientation(
                self.current_image_path,
                self.rotation_angle,
            )
            if outcome.warning_title and outcome.warning_message:
                self._show_warning(outcome.warning_title, outcome.warning_message)
            if outcome.new_orientation is None:
                return
        except Exception as exc:
            logger.error(
                "Failed to update EXIF orientation for %s",
                self.current_image_path,
                exc_info=exc,
            )
            self._show_error(
                "Error", f"Could not update the image rotation metadata: {exc}"
            )
            return

        self.manager.invalidate(self.current_image_path)
        self.rotation_angle = 0
        self.current_exif_orientation = outcome.new_orientation
        self.show_image(self.current_image_path, record_history=False)

    def print_tree_to_console(self, event=None) -> None:
        print_tree(self.defaults, self.original_tree.root, max_depth=9999)

    def reset_burst_cycle(self, event=None) -> None:
        """Reset the current burst queue when running the burst provider."""
        if self.providers.get_current_provider_name() != "burst":
            return
        if not getattr(self, "manager", None):
            return
        if self.manager.reset_provider():
            logger.debug("Burst cycle reset on demand.")
            self.next_image()
        else:
            logger.debug("Burst reset requested but provider lacks reset hook.")

    def clear_memory(self, event=None) -> None:
        self.folder_memory.clear()
        self.scope_seen_folders.clear()
        self._last_burst_memory_token = None
        self.manager.refresh_provider()
        self._sync_original_scope_state()
        logger.debug("Folder selection memory cleared for current scope.")

    def subfolder_mode_on(self) -> None:
        match self.navigation_mode:
            case "folder":
                folder: str = os.path.dirname(self.current_image_path)
                self._record_scope_entry(folder)
                self.subFolderStack.push(
                    ScopeStackEntry(
                        path=folder,
                        image_paths=self.image_paths[:],
                        scope_state=self._capture_scope_state(),
                    )
                )
                temp_image_paths: list[str] = utils.images_from_path(
                    os.path.dirname(self.current_image_path),
                    tree=self.original_tree,
                )
                temp_weights: list[int] = [1] * len(temp_image_paths)
                self.subfolder_mode = True
            case "branch":
                node: TreeNode = self.find_node_for_image(self.current_image_path)
                if not node:
                    logger.debug(
                        "subfolder_mode_on: No valid node found for current image."
                    )
                    return
                self._record_scope_entry(node.name)
                self.subFolderStack.push(
                    ScopeStackEntry(
                        path=node.name,
                        image_paths=self.image_paths[:],
                        scope_state=self._capture_scope_state(),
                    )
                )
                temp_image_paths, temp_weights = (
                    extract_image_paths_and_weights_from_tree(
                        tree=self.original_tree, start_node=node
                    )
                )
                self.subfolder_mode = True

        self.folder_memory = self._new_scope_memory()
        self.scope_seen_folders = set()
        self.update_slide_show(
            image_paths=temp_image_paths,
            selection_weights=SelectionWeights.from_weights(temp_weights),
            record_initial_history=True,
        )

    def subfolder_mode_off(self) -> None:
        scope_entry = self.subFolderStack.pop()
        if scope_entry is None:
            logger.warning("Cannot leave subfolder mode - scope stack is empty.")
            return
        self.image_paths = scope_entry.image_paths
        self.number_of_images = len(self.image_paths)
        self.subfolder_mode = False
        self._apply_scope_state(scope_entry.scope_state)
        self.update_slide_show(
            image_paths=self.image_paths,
            selection_weights=self.selection_weights,
            record_initial_history=True,
        )

    def select_mode(self, event=None) -> None:
        match event.char.upper():
            case "C":
                self.set_provider("random")
            case "L":
                self.set_provider("sequential", index=self.current_image_index + 1)
            case "W":
                self.set_provider("weighted")
            case "D":
                self.set_provider(
                    "controlled_random_weighted",
                    gap_min=3,
                )
            case "B":
                self.set_provider(
                    "burst",
                    burst_size=5,
                    index=self.current_image_index,
                )

    def toggle_mute(self, event=None) -> None:
        if hasattr(self, "video_player") and self.video_player:
            current_mute: bool = self.video_player.audio_get_mute()
            new_mute: bool = not current_mute
            self.video_player.audio_set_mute(new_mute)
            self.video_muted = new_mute

    def toggle_subfolder_mode(self, event=None) -> None:
        if not self.subfolder_mode:
            self.subfolder_mode_on()
        else:
            self.subfolder_mode_off()
        self.show_image(self.current_image_path, record_history=False)

    def toggle_navigation_mode(self, event=None) -> None:
        match self.navigation_mode:
            case "branch":
                self.navigation_node = None
                self.navigation_mode = "folder"
            case "folder":
                self.navigation_node: TreeNode = self.find_node_for_image(
                    self.current_image_path
                )
                if self.navigation_node:
                    self.navigation_mode = "branch"
                else:
                    (
                        logger.warning(
                            "Cannot change mode - %s not in tree",
                            self.current_image_path,
                        ),
                    )
                    return
        self.reset_parent_mode()
        self.update_filename_display()

    # -- Parent Mode Navigation ---

    def follow_branch_up(self, event=None) -> None:
        if self.subfolder_mode:
            self.subfolder_mode = False
            self.show_image(self.current_image_path, record_history=False)
            return
        self.navigate_up()

    def navigate_up(self) -> None:
        if self.parentFolderStack.is_full() or not self.parent_mode:
            logger.warning("Cannot navigate up - Stack is full or not in parent mode.")
            return

        current_path: str = os.path.dirname(self.current_image_path)
        child_path = None

        if self.navigation_mode == "folder":
            current_entry = self.parentFolderStack.peek()
            if current_entry is None or current_entry.path is None:
                logger.warning("Cannot navigate up - parent scope stack is empty.")
                return
            current_top = current_entry.path
            if utils.contains_subdirectory(current_top):
                current_path_level: int = utils.level_of(current_top)
                child_level: int = current_path_level + 1
                child_path: str = utils.truncate_path(current_path, child_level)

                previous_entry = self.parentFolderStack.peek(2)
                previous_path = previous_entry.path if previous_entry else None
                if child_path == previous_path:
                    self.step_backwards()
                    return
                elif not utils.contains_subdirectory(child_path):
                    self.toggle_subfolder_mode()
                else:
                    self._record_scope_entry(child_path)
                    self.parentFolderStack.push(
                        ScopeStackEntry(
                            path=child_path,
                            image_paths=self.image_paths[:],
                            scope_state=self._capture_scope_state(),
                        )
                    )
            else:
                logger.warning("No valid child directory found.")
        elif self.navigation_mode == "branch":
            current_path_node = self.original_tree.find_node(
                current_path, self.original_tree.path_lookup
            )
            path: list = []
            node: TreeNode = current_path_node
            while node and node != self.navigation_node:
                path.append(node)
                node = node.parent

            if node != self.navigation_node:
                logger.warning("No valid child node found in the branch.")
                return

            path.reverse()
            self.navigation_node = path[0] if path else self.navigation_node
            if self.navigation_node:
                self._record_scope_entry(self.navigation_node.name)

        self.folder_memory = self._new_scope_memory()
        self.scope_seen_folders = set()
        self.traverse_directory(
            child_path,
            self.navigation_node,
            record_initial_history=True,
        )

    def follow_branch_down(self, event=None) -> None:
        if self.subfolder_mode:
            self.toggle_subfolder_mode()
            return
        if self.parentFolderStack.is_full():
            logger.warning("Cannot navigate down - Stack is full.")
        else:
            self.navigate_down()

    def navigate_down(self) -> None:
        parent_path = None

        match (self.navigation_mode, self.parent_mode):
            case ("folder", False):
                current_path: str = os.path.dirname(self.current_image_path)
                current_path_level: int = utils.level_of(current_path)
                for i in range(current_path_level - 1, 1, -1):
                    parent_level: int = i
                    parent_path: str = utils.truncate_path(current_path, parent_level)
                    if utils.contains_subdirectory(
                        parent_path
                    ) > 1 or utils.contains_files(parent_path):
                        break
                self._record_scope_entry(parent_path)
                self.parentFolderStack.push(
                    ScopeStackEntry(
                        path=parent_path,
                        image_paths=self.image_paths[:],
                        scope_state=self._capture_scope_state(),
                    )
                )
            case ("folder", True):
                previous_entry = self.parentFolderStack.peek()
                if previous_entry is None or previous_entry.path is None:
                    logger.warning(
                        "Cannot navigate down - parent scope stack is empty."
                    )
                    return
                previous_path = previous_entry.path
                parent_level = utils.level_of(previous_path) - 1
                parent_path = utils.truncate_path(previous_path, parent_level)
                prior_entry = self.parentFolderStack.peek(2)
                prior_path = prior_entry.path if prior_entry else None
                if parent_path == prior_path:
                    self.step_backwards()
                    return
                self._record_scope_entry(parent_path)
                self.parentFolderStack.push(
                    ScopeStackEntry(
                        path=parent_path,
                        image_paths=self.image_paths[:],
                        scope_state=self._capture_scope_state(),
                    )
                )
            case ("branch", False):
                self.navigation_node = self.find_node_for_image(
                    self.current_image_path
                ).parent
                if self.navigation_node:
                    self._record_scope_entry(self.navigation_node.name)
            case ("branch", True):
                self.navigation_node = self.navigation_node.parent
                if self.navigation_node:
                    self._record_scope_entry(self.navigation_node.name)

        self.parent_mode = True
        self.folder_memory = self._new_scope_memory()
        self.scope_seen_folders = set()
        self.traverse_directory(
            parent_path,
            self.navigation_node,
            record_initial_history=True,
        )

    def step_backwards(self, event=None) -> None:
        if self.parentFolderStack.is_empty():
            logger.warning("Cannot step back - Stack is empty.")
            return
        scope_entry = self.parentFolderStack.pop()
        if scope_entry is None:
            logger.warning("Cannot step back - parent scope stack is empty.")
            return
        self._apply_scope_state(scope_entry.scope_state)
        self.update_slide_show(scope_entry.image_paths, self.selection_weights)

    def reset_parent_mode(self, event=None) -> None:
        self.parent_mode = False
        self.subfolder_mode = False
        self.parentFolderStack.clear()
        self.subFolderStack.clear()
        self.image_paths = self.original_image_paths[:]
        self.selection_weights = self.original_selection_weights.copy()
        self.folder_memory = self.original_folder_memory.copy()
        self.scope_seen_folders = set(self.original_scope_seen_folders)
        self._last_burst_memory_token = None
        self.update_slide_show(self.image_paths, self.selection_weights)
        self.show_image(self.image_paths[self.current_image_index], record_history=False)
        logger.debug("Parent mode reset and modes updated.")

    # --- Filename and Mode Display Methods ---

    def _format_rotation_display(self) -> str:
        exif_angle: int = ORIENTATION_TO_CW.get(self.current_exif_orientation, 0)
        manual_delta: int = (-self.rotation_angle) % 360
        if manual_delta:
            total_angle: int = (exif_angle + manual_delta) % 360
            return f"{total_angle}°"
        if exif_angle:
            return f"{exif_angle}° [EXIF]"
        return "0°"

    def toggle_filename_display(self, event=None) -> None:
        self.show_filename: bool = not self.show_filename
        self.update_filename_display()

    def update_filename_display(self) -> None:
        if self.show_filename:
            if not self.current_image_path or not self.image_paths:
                self.filename_label.place_forget()
                self.mode_label.place_forget()
                self.root.update_idletasks()
                return
            fixed_colour = None
            fixed_path = None
            self.filename_label.config(state=tk.NORMAL)
            self.filename_label.delete("1.0", tk.END)
            label_path: str = self.current_image_path
            if self.navigation_mode == "branch":
                label_path = os.path.join(
                    self.find_node_for_image(self.current_image_path).name,
                    os.path.basename(self.current_image_path),
                )

            match (self.navigation_mode, self.parent_mode, self.subfolder_mode):
                case ("folder", True, False):
                    parent_entry = self.parentFolderStack.peek()
                    fixed_path = parent_entry.path if parent_entry else None
                    fixed_colour = "gold"
                case ("folder", _, True):
                    subfolder_entry = self.subFolderStack.peek()
                    fixed_path = subfolder_entry.path if subfolder_entry else None
                    fixed_colour = "tomato"
                case ("branch", True, False):
                    fixed_path = self.navigation_node.name
                    fixed_colour = "lightgreen"
                case ("branch", _, True):
                    subfolder_entry = self.subFolderStack.peek()
                    if subfolder_entry is None or subfolder_entry.path is None:
                        fixed_path = None
                    else:
                        fixed_path = self.original_tree.find_node(
                            subfolder_entry.path, self.original_tree.node_lookup
                        ).name
                    fixed_colour = "tomato"

            if fixed_colour and fixed_path:
                if label_path.startswith(fixed_path):
                    fixed_portion: str = fixed_path
                    remaining_portion: str = label_path[len(fixed_path) :]
                else:
                    fixed_portion = ""
                    remaining_portion = label_path

                self.filename_label.insert(tk.END, fixed_portion, "fixed")
                self.filename_label.insert(tk.END, remaining_portion, "normal")
            else:
                self.filename_label.insert(tk.END, label_path, "normal")
                fixed_colour = "white"

            rotation_text: str = self._format_rotation_display()
            zoom_percent: int = (
                self.zoompan.get_zoom_percent()
                if hasattr(self, "zoompan") and self.zoompan
                else 100
            )
            meta_text: str = f" ({rotation_text}, {zoom_percent}%)"
            self.filename_label.insert(tk.END, meta_text, "meta")

            self.filename_label.tag_configure("fixed", foreground=fixed_colour)
            self.filename_label.tag_configure("normal", foreground="white")
            self.filename_label.tag_configure("meta", foreground="white")
            self.filename_label.place(x=0, y=0)
            full_label_text: str = self.filename_label.get("1.0", "end-1c")
            self.filename_label.config(
                height=1, width=len(full_label_text) + 10, bg="black"
            )
            self.filename_label.config(state=tk.DISABLED)

            provider_label: str = self._provider_display_name() if self.mode else "-"
            scope_parts: list[str] = []
            if self.subfolder_mode:
                scope_parts.append("SUB")
            if self.parent_mode:
                scope_parts.append("PAR")

            count = len(self.image_paths)
            if self.current_image_path in self.image_paths:
                idx = self.image_paths.index(self.current_image_path) + 1
            else:
                idx = max(1, min(self.current_image_index + 1, count))
            count_text = f"({idx}/{count})"
            crw_text = self._crw_status_text()

            mode_parts = [count_text]
            if crw_text:
                mode_parts.append(crw_text)
            if scope_parts:
                mode_parts.append(" ".join(scope_parts))
            mode_parts.append(provider_label)
            mode_text = " ".join(mode_parts)

            display_text: str = mode_text
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

    def rotate_image(self, event=None) -> None:
        self.rotation_angle = (self.rotation_angle - 90) % 360
        self.show_image(self.current_image_path, record_history=False)

    # --- Exit Method ---

    def exit_slideshow(self, event=None) -> None:
        self.manager.lru_cache.clear()
        self.manager.preload_queue.clear()
        self._release_video_resources()
        if hasattr(self, "vlc_instance") and self.vlc_instance:
            self.vlc_instance.release()
            self.vlc_instance = None
        if hasattr(self, "video_frame"):
            self.video_frame.destroy()
        self.root.destroy()
