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
    SelectionScope,
    apply_mode_and_recalculate_scope,
    build_tree,
    extract_selection_scope_from_tree,
)
from enkan.tree.diagnostics import print_tree
from enkan.mySlideshow.Gui.Gui import Gui
from enkan.mySlideshow.MediaFileOps import (
    ORIENTATION_TO_CW,
    delete_media_file,
    write_exif_orientation,
)
from enkan.mySlideshow.NavigationTypes import (
    NavigationBasis,
    NavigationState,
    ScopeKind,
)
from enkan.mySlideshow.StatusBar import (
    StatusBarContext,
    build_filename_display,
    build_mode_text,
)
from enkan.mySlideshow.ScopeStack import ScopeStack, ScopeStackEntry
from enkan.mySlideshow.ZoomPan import ZoomPan

# Configure logging
logger: logging.Logger = logging.getLogger("enkan.ui")


@dataclass
class _ScopeState:
    selection_weights: SelectionWeights
    folder_memory: FolderSelectionMemory
    navigation_state: NavigationState
    selection_scope: SelectionScope | None = None
    seen_folders: set[str] = field(default_factory=set)


class ImageSlideshow:
    def __init__(
        self,
        root: TreeNode,
        tree: Tree,
        image_paths: list,
        selection_weights: SelectionWeights,
        selection_scope: SelectionScope | None,
        defaults: Defaults,
        filters: Filters,
        interval: int | float | None = None,
    ) -> None:
        self.root: TreeNode = root
        self.original_tree: Tree = tree
        self.image_paths: list = image_paths
        self.selection_weights: SelectionWeights = selection_weights.copy()
        self.original_selection_weights: SelectionWeights = selection_weights.copy()
        self.selection_scope: SelectionScope = (
            selection_scope.copy()
            if selection_scope is not None
            else SelectionScope.from_parts(
                image_paths,
                self.selection_weights.weights,
                cum_weights=self.selection_weights.cum_weights,
            )
        )
        self.original_selection_scope: SelectionScope = self.selection_scope.copy()
        self.folder_memory: FolderSelectionMemory = self._new_scope_memory()
        self.original_folder_memory: FolderSelectionMemory = self.folder_memory.copy()
        self.scope_seen_folders: set[str] = set()
        self.original_scope_seen_folders: set[str] = set()
        self.original_navigation_state = NavigationState(
            basis=NavigationBasis.FOLDER,
            scope_kind=ScopeKind.ROOT,
        )
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
        self.current_provider_status_payload = None

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
        self.root.bind("<D>", self.toggle_provider_display_mode)
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
            navigation_state=self._navigation_state(),
            selection_scope=(
                self.selection_scope.copy()
                if getattr(self, "selection_scope", None) is not None
                else None
            ),
            seen_folders=set(self.scope_seen_folders),
        )

    def _navigation_node_from_anchor(self, branch_anchor: str | None) -> TreeNode | None:
        if not branch_anchor:
            return None
        if not getattr(self, "original_tree", None):
            return None
        return self.original_tree.find_node(branch_anchor, self.original_tree.node_lookup)

    def _apply_navigation_state(self, navigation_state: NavigationState) -> None:
        self.navigation_mode = navigation_state.basis.value
        self.parent_mode = navigation_state.is_parent
        self.subfolder_mode = navigation_state.is_subfolder
        self.navigation_node = self._navigation_node_from_anchor(
            navigation_state.branch_anchor
        )

    def _apply_scope_state(self, scope_state: _ScopeState) -> None:
        self.selection_weights = scope_state.selection_weights.copy()
        selection_scope = getattr(scope_state, "selection_scope", None)
        if selection_scope is not None:
            self.selection_scope = selection_scope.copy()
        self.folder_memory = scope_state.folder_memory.copy()
        self.scope_seen_folders = set(scope_state.seen_folders)
        self._apply_navigation_state(scope_state.navigation_state)
        self._last_burst_memory_token = None

    def _sync_original_scope_structure(self) -> None:
        if self.parent_mode or self.subfolder_mode:
            return
        self.original_image_paths = self.image_paths[:]
        self.original_selection_weights = self.selection_weights.copy()
        if getattr(self, "selection_scope", None) is not None:
            self.original_selection_scope = self.selection_scope.copy()
        self._sync_original_navigation_state()

    def _sync_original_navigation_state(self) -> None:
        if self.parent_mode or self.subfolder_mode:
            return
        self.original_navigation_state = self._navigation_state()

    def _sync_original_scope_memory(self) -> None:
        if self.parent_mode or self.subfolder_mode:
            return
        self.original_folder_memory = self.folder_memory.copy()
        self.original_scope_seen_folders = set(self.scope_seen_folders)

    def _sync_original_scope_state(self) -> None:
        self._sync_original_scope_structure()
        self._sync_original_scope_memory()

    def _navigation_basis(self) -> NavigationBasis:
        return NavigationBasis(getattr(self, "navigation_mode", "folder"))

    def _scope_kind(self) -> ScopeKind:
        if getattr(self, "subfolder_mode", False):
            return ScopeKind.SUBFOLDER
        if getattr(self, "parent_mode", False):
            return ScopeKind.PARENT
        return ScopeKind.ROOT

    def _navigation_state(self) -> NavigationState:
        return NavigationState(
            basis=self._navigation_basis(),
            scope_kind=self._scope_kind(),
            branch_anchor=(
                self.navigation_node.name if getattr(self, "navigation_node", None) else None
            ),
        )

    def _set_scope_kind(self, scope_kind: ScopeKind) -> None:
        self.parent_mode = scope_kind is ScopeKind.PARENT
        self.subfolder_mode = scope_kind is ScopeKind.SUBFOLDER

    def _scope_records_once_per_folder(self) -> bool:
        return self._navigation_state().scope_kind is not ScopeKind.ROOT

    def _resolve_memory_key_for_scope(self, scope_path: str | None) -> str | None:
        if not scope_path:
            return None
        tree = getattr(self, "original_tree", None)
        if tree is None:
            return scope_path
        node = tree.find_node(scope_path, tree.node_lookup)
        if node is None:
            node = tree.find_node(scope_path, tree.path_lookup)
        if node is not None:
            return node.name
        return scope_path

    def _resolve_memory_key_for_image(
        self,
        image_path: str,
        provider_pick_meta: dict[str, object] | None = None,
    ) -> str | None:
        if provider_pick_meta is not None:
            memory_key = provider_pick_meta.get("memory_key")
            if isinstance(memory_key, str) and memory_key:
                return memory_key
        providers = getattr(self, "providers", None)
        if providers is None:
            return os.path.dirname(image_path) or None
        return providers.resolve_memory_key_for_image(
            image_path,
            selection_scope=getattr(self, "selection_scope", None),
            tree=getattr(self, "original_tree", None),
        )

    def _record_scope_entry(self, folder: str) -> None:
        memory_key = self._resolve_memory_key_for_scope(folder)
        if not memory_key:
            return
        self.folder_memory.record_folder(memory_key)
        self._sync_original_scope_memory()

    def _record_memory_for_view(
        self,
        image_path: str,
        record_history: bool,
        provider_pick_meta: dict[str, object] | None = None,
    ) -> None:
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
            memory_key = self._resolve_memory_key_for_scope(burst_folder or folder)
            if not memory_key:
                return
            self.folder_memory.record_folder(memory_key)
            self._sync_original_scope_memory()
            return

        memory_key = self._resolve_memory_key_for_image(image_path, provider_pick_meta)
        if not memory_key:
            return

        if self._scope_records_once_per_folder():
            if memory_key in self.scope_seen_folders:
                return
            self.scope_seen_folders.add(memory_key)

        self.folder_memory.record_folder(memory_key)
        self._sync_original_scope_memory()

    def show_image(self, image_path: str = None, record_history: bool = True) -> None:
        # Stop existing video playback and clean up resources
        self._release_video_resources()
        if hasattr(self, "video_frame"):
            self.video_frame.place_forget()

        previous_image_path = getattr(self, "current_image_path", None)
        previous_provider_status_payload = getattr(
            self,
            "current_provider_status_payload",
            None,
        )

        image_path, media_payload = self.manager.get_next(
            image_path, record_history=record_history
        )
        if not image_path:
            logger.warning("No displayable media available.")
            return
        provider_pick_meta = getattr(self.manager, "current_media_metadata", None)

        self.current_image_path: str = image_path
        provider_pick_index = None
        if isinstance(provider_pick_meta, dict):
            raw_pick_index = provider_pick_meta.get("index")
            if isinstance(raw_pick_index, int):
                provider_pick_index = raw_pick_index
        if provider_pick_index is not None and 0 <= provider_pick_index < len(self.image_paths):
            self.current_image_index = provider_pick_index
        elif image_path in self.image_paths:
            self.current_image_index = self.image_paths.index(image_path)
        if not record_history and image_path == previous_image_path:
            self.current_provider_status_payload = previous_provider_status_payload
        elif (
            self.providers.get_current_provider_name() == "controlled_random_weighted"
            and self.providers.get_current_provider_display_mode() != "off"
        ):
            self.current_provider_status_payload = (
                self.providers.get_current_provider_status_payload(
                    image_paths=self.image_paths,
                    weights=self.selection_weights.weights,
                    selection_scope=getattr(self, "selection_scope", None),
                    current_image_path=self.current_image_path,
                    target_image_path=image_path,
                    folder_memory=self.folder_memory,
                    current_pick_meta=provider_pick_meta,
                    tree=self.original_tree,
                )
            )
        else:
            self.current_provider_status_payload = None
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
        self._record_memory_for_view(image_path, record_history, provider_pick_meta)

    def next_image(self, event=None) -> None:
        if self.rotation_angle != 0:
            self.rotation_angle = 0
        self.show_image()
        self.reset_auto_advance()

    def _provider_kwargs(self) -> dict[str, object]:
        return {
            **self.selection_weights.provider_kwargs(),
            "selection_scope": getattr(self, "selection_scope", None),
            "folder_memory": self.folder_memory,
            "tree": self.original_tree,
        }

    def update_slide_show(
        self,
        image_paths: list,
        selection_weights: SelectionWeights,
        selection_scope: SelectionScope | None = None,
        record_initial_history: bool = False,
        preferred_index: int | None = None,
    ) -> None:
        """Updates the slideshow with the new set of images and weights."""
        history_snapshot = (
            self.manager.history_snapshot() if getattr(self, "manager", None) else None
        )
        self.image_paths = image_paths
        self.selection_weights = selection_weights.copy()
        if selection_scope is not None:
            self.selection_scope = selection_scope.copy()
        elif getattr(self, "selection_scope", None) is not None:
            self.selection_scope = self.selection_scope.copy()
        else:
            self.selection_scope = SelectionScope.from_parts(
                image_paths,
                self.selection_weights.weights,
                cum_weights=self.selection_weights.cum_weights,
            )
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
        self.current_provider_status_payload = None
        self.show_image(
            self.image_paths[self.current_image_index],
            record_history=record_initial_history,
        )

    # --- Provider and Display Pipeline ---

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

    # --- Provider Selection and Mode Recalculation ---

    def set_provider(self, provider_name: str, **provider_kwargs) -> None:
        # Easily switch to any provider by name/key
        history_snapshot = (
            self.manager.history_snapshot() if getattr(self, "manager", None) else None
        )
        if provider_name == "controlled_random_weighted":
            provider_kwargs.setdefault("gap_min", 3)
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

    def toggle_provider_display_mode(self, event=None) -> None:
        current_mode = self.providers.cycle_current_provider_display_mode()
        logger.debug(
            "Provider display mode set to %s.",
            current_mode,
        )
        self.update_filename_display()

    def find_node_for_image(self, image_path: str) -> TreeNode | None:
        return self.original_tree.resolve_node_for_image(image_path)

    def find_container_node_for_image(self, image_path: str) -> TreeNode | None:
        return self.original_tree.resolve_container_node_for_image(image_path)

    def _current_branch_context_node(self, image_path: str | None = None) -> TreeNode | None:
        if self._navigation_basis() is not NavigationBasis.BRANCH:
            return None
        return self.find_node_for_image(image_path or self.current_image_path)

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
            selection_scope = extract_selection_scope_from_tree(
                tree=self.original_tree,
                start_node=navigation_node,
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
            selection_scope = extract_selection_scope_from_tree(
                parent_tree
            )
        else:
            logger.debug("No valid directory found.")
            return
        self.update_slide_show(
            selection_scope.image_paths,
            SelectionWeights.from_parts(
                selection_scope.weights,
                selection_scope.cum_weights,
            ),
            selection_scope=selection_scope,
            record_initial_history=record_initial_history,
        )

    # --- Dynamic Mode Adjustment ---

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
        selection_scope = apply_mode_and_recalculate_scope(
            self.original_tree,
            self.defaults,
            ignore_user_proportion=ignore_user,
        )
        self.original_image_paths = selection_scope.image_paths[:]
        self.folder_memory = self._new_scope_memory()
        self.scope_seen_folders = set()
        self.original_selection_weights = SelectionWeights.from_parts(
            selection_scope.weights,
            selection_scope.cum_weights,
        )
        self.original_selection_scope = selection_scope.copy()
        self.original_folder_memory = self.folder_memory.copy()
        self.original_scope_seen_folders = set()
        self.update_slide_show(
            selection_scope.image_paths,
            SelectionWeights.from_parts(
                selection_scope.weights,
                selection_scope.cum_weights,
            ),
            selection_scope=selection_scope,
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

    # --- UI Messaging and User Actions ---

    def _confirm_action(self, title: str, message: str) -> bool:
        return bool(self.gui.messagebox(title=title, message=message, type_="yesno"))

    def _show_error(self, title: str, message: str) -> None:
        self.gui.messagebox(title, message, icon="error")

    def _show_warning(self, title: str, message: str) -> None:
        self.gui.messagebox(title, message, icon="warning")

    def select_mode(self, event=None) -> None:
        match event.char.upper():
            case "C":
                self.set_provider("random")
            case "L":
                self.set_provider("sequential", index=self.current_image_index + 1)
            case "W":
                self.set_provider("weighted")
            case "D":
                if self.providers.get_current_provider_name() == "controlled_random_weighted":
                    current_settings = self.providers.get_current_provider_settings()
                    current_bucket_mode = str(current_settings.get("bucket_mode", "balance_bucket"))
                    next_bucket_mode = (
                        "folder_bucket"
                        if current_bucket_mode == "balance_bucket"
                        else "balance_bucket"
                    )

                    self.set_provider(
                        "controlled_random_weighted",
                        gap_min=int(current_settings.get("gap_min", 3)),
                        repeat_penalty=float(current_settings.get("repeat_penalty", 0.1)),
                        bucket_mode=next_bucket_mode,
                    )
                else:
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
                    if getattr(self, "selection_scope", None) is not None:
                        self.selection_scope.remove_at(index)
                    try:
                        self.manager.history_manager.remove(deleted_path)
                    except ValueError:
                        logger.debug(
                            "Deleted path was not present in history: %s",
                            deleted_path,
                        )
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
                        selection_scope=getattr(self, "selection_scope", None),
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

    def rotate_image(self, event=None) -> None:
        self.rotation_angle = (self.rotation_angle - 90) % 360
        self.show_image(self.current_image_path, record_history=False)

    def toggle_mute(self, event=None) -> None:
        if hasattr(self, "video_player") and self.video_player:
            current_mute: bool = self.video_player.audio_get_mute()
            new_mute: bool = not current_mute
            self.video_player.audio_set_mute(new_mute)
            self.video_muted = new_mute

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
        self._sync_original_scope_memory()
        logger.debug("Folder selection memory cleared for current scope.")

    def toggle_filename_display(self, event=None) -> None:
        self.show_filename: bool = not self.show_filename
        self.update_filename_display()

    # --- Scope Navigation ---

    def subfolder_mode_on(self) -> None:
        match self._navigation_basis():
            case NavigationBasis.FOLDER:
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
                    folder,
                    tree=self.original_tree,
                )
                temp_weights: list[int] = [1] * len(temp_image_paths)
                folder_node = self.original_tree.find_node(
                    folder,
                    self.original_tree.path_lookup,
                )
                node_key = self._resolve_memory_key_for_scope(folder) or folder
                node_level = folder_node.level if folder_node is not None else 1
                ancestor_keys = None
                if folder_node is not None:
                    lineage: list[str] = []
                    node_cursor = folder_node
                    while node_cursor is not None:
                        lineage.append(node_cursor.name)
                        node_cursor = node_cursor.parent
                    lineage.reverse()
                    ancestor_keys = tuple(lineage)
                selection_scope = SelectionScope.single_unit(
                    node_key=node_key,
                    image_paths=temp_image_paths,
                    weights=temp_weights,
                    node_level=node_level,
                    ancestor_keys=ancestor_keys,
                )
            case NavigationBasis.BRANCH:
                node = self._current_branch_context_node(self.current_image_path)
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
                selection_scope = extract_selection_scope_from_tree(
                    tree=self.original_tree,
                    start_node=node,
                )
        self._set_scope_kind(ScopeKind.SUBFOLDER)

        self.folder_memory = self._new_scope_memory()
        self.scope_seen_folders = set()
        self.update_slide_show(
            image_paths=selection_scope.image_paths,
            selection_weights=SelectionWeights.from_parts(
                selection_scope.weights,
                selection_scope.cum_weights,
            ),
            selection_scope=selection_scope,
            record_initial_history=True,
        )

    def subfolder_mode_off(self) -> None:
        scope_entry = self.subFolderStack.pop()
        if scope_entry is None:
            logger.warning("Cannot leave subfolder mode - scope stack is empty.")
            return
        self.image_paths = scope_entry.image_paths
        self.number_of_images = len(self.image_paths)
        self._apply_scope_state(scope_entry.scope_state)
        self.update_slide_show(
            image_paths=self.image_paths,
            selection_weights=self.selection_weights,
            record_initial_history=True,
        )

    def toggle_subfolder_mode(self, event=None) -> None:
        if not self.subfolder_mode:
            self.subfolder_mode_on()
        else:
            self.subfolder_mode_off()
        self.show_image(self.current_image_path, record_history=False)

    def toggle_navigation_mode(self, event=None) -> None:
        match self._navigation_basis():
            case NavigationBasis.BRANCH:
                self.navigation_node = None
                self.navigation_mode = NavigationBasis.FOLDER.value
            case NavigationBasis.FOLDER:
                if self.find_node_for_image(self.current_image_path):
                    self.navigation_node = None
                    self.navigation_mode = NavigationBasis.BRANCH.value
                else:
                    (
                        logger.warning(
                            "Cannot change mode - %s not in tree",
                            self.current_image_path,
                        ),
                    )
                    return
        self.reset_parent_mode(preserve_navigation_state=True)
        self.update_filename_display()

    # -- Parent Mode Navigation ---

    def follow_branch_up(self, event=None) -> None:
        if self.subfolder_mode:
            self._set_scope_kind(ScopeKind.ROOT)
            self.show_image(self.current_image_path, record_history=False)
            return
        self.navigate_up()

    def navigate_up(self) -> None:
        if self.parentFolderStack.is_full() or not self.parent_mode:
            logger.warning("Cannot navigate up - Stack is full or not in parent mode.")
            return

        current_path: str = os.path.dirname(self.current_image_path)
        child_path = None
        nav_state = self._navigation_state()

        if nav_state.is_folder:
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
        elif nav_state.is_branch:
            current_path_node = self._current_branch_context_node(self.current_image_path)
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
        nav_state = self._navigation_state()

        match (nav_state.basis, nav_state.scope_kind):
            case (NavigationBasis.FOLDER, ScopeKind.ROOT):
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
            case (NavigationBasis.FOLDER, ScopeKind.PARENT):
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
            case (NavigationBasis.BRANCH, ScopeKind.ROOT):
                current_node = self._current_branch_context_node(self.current_image_path)
                self.navigation_node = current_node.parent if current_node else None
                if self.navigation_node:
                    self._record_scope_entry(self.navigation_node.name)
            case (NavigationBasis.BRANCH, ScopeKind.PARENT):
                self.navigation_node = self.navigation_node.parent
                if self.navigation_node:
                    self._record_scope_entry(self.navigation_node.name)

        self._set_scope_kind(ScopeKind.PARENT)
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

    def reset_parent_mode(self, event=None, preserve_navigation_state: bool = False) -> None:
        self.parentFolderStack.clear()
        self.subFolderStack.clear()
        self.image_paths = self.original_image_paths[:]
        self.selection_weights = self.original_selection_weights.copy()
        if getattr(self, "original_selection_scope", None) is not None:
            self.selection_scope = self.original_selection_scope.copy()
        self.folder_memory = self.original_folder_memory.copy()
        self.scope_seen_folders = set(self.original_scope_seen_folders)
        self._last_burst_memory_token = None
        if preserve_navigation_state:
            self._set_scope_kind(ScopeKind.ROOT)
            self._sync_original_navigation_state()
        else:
            self._apply_navigation_state(self.original_navigation_state)
        self.update_slide_show(self.image_paths, self.selection_weights)
        self.show_image(self.image_paths[self.current_image_index], record_history=False)
        logger.debug("Parent mode reset and modes updated.")

    # --- Status-Bar Display ---

    def _format_rotation_display(self) -> str:
        exif_angle: int = ORIENTATION_TO_CW.get(self.current_exif_orientation, 0)
        manual_delta: int = (-self.rotation_angle) % 360
        if manual_delta:
            total_angle: int = (exif_angle + manual_delta) % 360
            return f"{total_angle}°"
        if exif_angle:
            return f"{exif_angle}° [EXIF]"
        return "0°"

    def _status_label_path(self) -> str:
        label_path = self.current_image_path
        if self._navigation_state().is_branch:
            branch_node = self._current_branch_context_node(self.current_image_path)
            if branch_node:
                label_path = os.path.join(
                    branch_node.name,
                    os.path.basename(self.current_image_path),
                )
        return label_path

    def _status_fixed_path_and_colour(self) -> tuple[str | None, str | None]:
        fixed_path = None
        fixed_colour = None
        nav_state = self._navigation_state()

        match (nav_state.basis, nav_state.scope_kind):
            case (NavigationBasis.FOLDER, ScopeKind.PARENT):
                parent_entry = self.parentFolderStack.peek()
                fixed_path = parent_entry.path if parent_entry else None
                fixed_colour = "gold"
            case (NavigationBasis.FOLDER, ScopeKind.SUBFOLDER):
                subfolder_entry = self.subFolderStack.peek()
                fixed_path = subfolder_entry.path if subfolder_entry else None
                fixed_colour = "tomato"
            case (NavigationBasis.BRANCH, ScopeKind.PARENT):
                fixed_path = nav_state.branch_anchor
                fixed_colour = "lightgreen"
            case (NavigationBasis.BRANCH, ScopeKind.SUBFOLDER):
                subfolder_entry = self.subFolderStack.peek()
                if subfolder_entry is None or subfolder_entry.path is None:
                    fixed_path = None
                else:
                    fixed_path = self.original_tree.find_node(
                        subfolder_entry.path, self.original_tree.node_lookup
                    ).name
                fixed_colour = "tomato"

        return fixed_path, fixed_colour

    def _status_context(self) -> StatusBarContext:
        fixed_path, fixed_colour = self._status_fixed_path_and_colour()
        provider_status_payload = (
            self.current_provider_status_payload
            or self.providers.get_current_provider_status_payload(
                image_paths=self.image_paths,
                weights=self.selection_weights.weights,
                selection_scope=getattr(self, "selection_scope", None),
                current_image_path=self.current_image_path,
                folder_memory=self.folder_memory,
                tree=self.original_tree,
            )
        )
        return StatusBarContext(
            label_path=self._status_label_path(),
            fixed_path=fixed_path,
            fixed_colour=fixed_colour,
            rotation_text=self._format_rotation_display(),
            zoom_percent=(
                self.zoompan.get_zoom_percent()
                if hasattr(self, "zoompan") and self.zoompan
                else 100
            ),
            current_image_path=self.current_image_path,
            image_paths=self.image_paths,
            current_image_index=self.current_image_index,
            provider_enabled=bool(self.mode),
            provider_label=self.providers.get_current_provider_label(),
            provider_status_text=self.providers.get_current_provider_status(
                display_mode=self.providers.get_current_provider_display_mode(),
                status_payload=provider_status_payload,
            ),
            subfolder_mode=self.subfolder_mode,
            parent_mode=self.parent_mode,
            auto_advance_running=bool(getattr(self, "auto_advance_running", False)),
            auto_advance_interval=getattr(self, "auto_advance_interval", None),
        )

    def update_filename_display(self) -> None:
        if self.show_filename:
            if not self.current_image_path or not self.image_paths:
                self.filename_label.place_forget()
                self.mode_label.place_forget()
                self.root.update_idletasks()
                return

            status_context = self._status_context()
            filename_display = build_filename_display(status_context)
            mode_text = build_mode_text(status_context)

            self.filename_label.config(state=tk.NORMAL)
            self.filename_label.delete("1.0", tk.END)
            for segment in filename_display.segments:
                self.filename_label.insert(tk.END, segment.text, segment.tag)

            self.filename_label.tag_configure(
                "fixed", foreground=filename_display.fixed_colour
            )
            self.filename_label.tag_configure("normal", foreground="white")
            self.filename_label.tag_configure("meta", foreground="white")
            self.filename_label.place(x=0, y=0)
            self.filename_label.config(height=1, width=filename_display.width, bg="black")
            self.filename_label.config(state=tk.DISABLED)

            self.mode_label.config(
                text=mode_text,
                fg="white",
            )
            self.mode_label.place(x=self.root.winfo_screenwidth(), y=0, anchor="ne")
        else:
            self.filename_label.place_forget()
            self.mode_label.place_forget()
        self.root.update_idletasks()

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
