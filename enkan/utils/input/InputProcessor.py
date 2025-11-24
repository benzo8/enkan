import os
from typing import Dict, List, Any, Callable, Optional, Tuple
import logging
from tqdm import tqdm

from enkan import constants
from enkan.tree.Tree import Tree
from enkan.utils import utils
from enkan.utils.Defaults import Mode

logger: logging.Logger = logging.getLogger(__name__)


class InputProcessor:
    def __init__(self, defaults, filters):
        self.defaults = defaults
        self.filters = filters
        self.detected_mode = None
        self.detected_lowest = None

    def process_input(
        self,
        input_entry,
        recdepth: int = 1,
        graft_offset: int = 0,
        apply_global_mode: bool = True,
        nested_file_handler: Optional[
            Callable[[str, int, bool], Tuple[Dict, Dict, List, List]]
        ] = None,
    ):
        """
        Parse a .txt entry into image_dirs/specific_images structures.
        Returns (image_dirs, specific_images, all_images, weights) for compatibility.
        """
        image_dirs: Dict = {}
        specific_images: Dict = {}
        all_images: List = []
        weights: List = []
        # reset detected mode for this run
        self.detected_mode = None
        self.detected_lowest = None

        self._process_entry(
            input_entry,
            recdepth,
            image_dirs,
            specific_images,
            all_images,
            weights,
            graft_offset,
            apply_global_mode,
            nested_file_handler,
        )
        return image_dirs, specific_images, all_images, weights

    def _process_entry(
        self,
        entry,
        recdepth,
        image_dirs,
        specific_images,
        all_images,
        weights,
        graft_offset: int = 0,
        apply_global_mode: bool = True,
        nested_file_handler: Optional[
            Callable[[str, int, bool], Tuple[Dict, Dict, List, List]]
        ] = None,
    ) -> Tree | None:
        """
        Process a single input entry (file, directory, or image).
        """

        additional_search_paths = [os.path.dirname(entry)]
        if os.path.isabs(entry) and os.path.isfile(entry):
            input_filename_full = entry
        else:
            input_filename_full = utils.find_input_file(entry, additional_search_paths)

        if input_filename_full:
            ext = os.path.splitext(input_filename_full)[1].lower()
            if ext != ".txt":
                if nested_file_handler and ext in {".lst", ".tree"}:
                    nested_result = nested_file_handler(
                        input_filename_full, graft_offset, apply_global_mode
                    )
                    if nested_result:
                        n_image_dirs, n_specific_images, n_all_images, n_weights = (
                            nested_result
                        )
                        image_dirs.update(n_image_dirs or {})
                        specific_images.update(n_specific_images or {})
                        all_images.extend(n_all_images or [])
                        weights.extend(n_weights or [])
                    return None
                logger.warning(
                    "Skipping non-txt input '%s' in InputProcessor.",
                    input_filename_full,
                )
                return None
            with open(input_filename_full, "r", buffering=65536, encoding="utf-8") as f:
                total_lines = sum(1 for _ in f)
                f.seek(0)
                for line in tqdm(
                    f,
                    desc=f"Parsing {input_filename_full}",
                    leave=True,
                    unit="line",
                    total=total_lines,
                ):
                    line = line.strip()
                    if not line or line.startswith("#"):  # Skip comments/empty lines
                        continue
                    line = line.replace('"', "").strip()  # Remove enclosing quotes

                    line_ext = os.path.splitext(line)[1].lower()
                    if utils.is_textfile(line):
                        # Recursively process nested text files
                        sub_image_dirs, sub_specific_images, _, _ = self.process_input(
                            line,
                            recdepth + 1,
                            graft_offset=graft_offset,
                            apply_global_mode=apply_global_mode,
                            nested_file_handler=nested_file_handler,
                        )
                        image_dirs.update(sub_image_dirs)
                        specific_images.update(sub_specific_images)
                    elif line_ext in {".lst", ".tree"} and nested_file_handler:
                        nested_result = nested_file_handler(
                            line, graft_offset, apply_global_mode
                        )
                        if nested_result:
                            n_image_dirs, n_specific_images, n_all_images, n_weights = (
                                nested_result
                            )
                            image_dirs.update(n_image_dirs or {})
                            specific_images.update(n_specific_images or {})
                            all_images.extend(n_all_images or [])
                            weights.extend(n_weights or [])
                    elif line_ext in {".lst", ".tree"}:
                        logger.warning(
                            "Nested input '%s' requires external handler; skipping.",
                            line,
                        )
                    else:
                        path, modifier_list = self.parse_input_line(
                            line,
                            recdepth,
                            graft_offset=graft_offset,
                            apply_global_mode=apply_global_mode,
                        )
                        if modifier_list:
                            if utils.is_imagefile(path):
                                specific_images[path] = modifier_list
                            else:
                                image_dirs[path] = modifier_list
        else:  # Handle directories and images directly
            path, modifier_list = self.parse_input_line(
                entry,
                recdepth,
                graft_offset=graft_offset,
                apply_global_mode=apply_global_mode,
            )
            if modifier_list:
                if utils.is_imagefile(path):
                    specific_images[path] = modifier_list
                else:
                    image_dirs[path] = modifier_list

    def parse_input_line(
        self, line, recdepth, graft_offset: int = 0, apply_global_mode: bool = True
    ):
        if line.startswith("[r]"):
            self.defaults.set_global_defaults(is_random=True)
            return None, None

        # Handle filters
        if line.startswith("[+]"):
            keyword: str = line[3:].strip()
            self.filters.add_must_contain(keyword)
            return None, None
        elif line.startswith("[-]"):
            path_or_keyword: str = line[3:].strip()
            if os.path.isabs(path_or_keyword):
                if os.path.isfile(path_or_keyword):
                    self.filters.add_ignored_file(path_or_keyword)
                else:
                    self.filters.add_ignored_dir(path_or_keyword)
            else:
                self.filters.add_must_not_contain(path_or_keyword)
            return None, None

        # Strip quotes early (if users quote paths)
        line = line.replace('"', "").strip()

        # Extract all modifiers
        modifiers = constants.MODIFIER_PATTERN.findall(line)
        # Remove all modifiers from the line to get the path
        path = constants.MODIFIER_PATTERN.sub("", line).strip()

        # Defaults/state container (handlers mutate this)
        # Can be global: video, mute, mode_modifier, dont_recurse
        # Can be inherited: weight_modifier, is_percentage, video
        # Node-only: proportion, graft_level, group, flat
        state: dict[str, Any] = {
            "weight_modifier": 100,
            "proportion": None,
            "user_proportion": None,
            "is_percentage": True,
            "graft_level": None,
            "group": None,
            "mode_modifier": None,
            "flat": False,
            "video": None,
            "mute": None,
            "dont_recurse": None,
        }

        def handle_weight(s: str):
            if s.endswith("%"):
                state["weight_modifier"] = int(s[:-1])
                state["is_percentage"] = True
            else:
                state["weight_modifier"] = int(s)
                state["is_percentage"] = False

        def handle_proportion(s: str):
            # strip leading/trailing %: e.g. %33% or %10
            value = int(s.strip("%"))
            state["proportion"] = value
            state["user_proportion"] = value

        def handle_graft(s: str):
            state["graft_level"] = int(s[1:])

        def handle_group(s: str):
            state["group"] = s[1:]

        def handle_mode(s: str):
            state["mode_modifier"] = Mode.from_string(s).map

        def handle_flat(_s: str):
            state["flat"] = True

        def handle_video(_s: str):
            state["video"] = True

        def handle_no_video(_s: str):
            state["video"] = False

        def handle_mute(_s: str):
            state["mute"] = True

        def handle_no_mute(_s: str):
            state["mute"] = False

        def handle_dont_recurse(_s: str):
            state["dont_recurse"] = True
            self.filters.add_dont_recurse_beyond_folder(path)

        # Ordered list of (pattern, handler)
        HANDLERS = (
            (constants.WEIGHT_MODIFIER_PATTERN, handle_weight),
            (constants.PROPORTION_PATTERN, handle_proportion),
            (constants.GRAFT_PATTERN, handle_graft),
            (constants.GROUP_PATTERN, handle_group),
            (constants.MODE_PATTERN, handle_mode),
            (constants.FLAT_PATTERN, handle_flat),
            (constants.VIDEO_PATTERN, handle_video),
            (constants.NO_VIDEO_PATTERN, handle_no_video),
            (constants.MUTE_PATTERN, handle_mute),
            (constants.NO_MUTE_PATTERN, handle_no_mute),
            (constants.DONT_RECURSE_PATTERN, handle_dont_recurse),
        )

        for mod in modifiers:
            mod_content = mod.strip("[]").strip()
            for pattern, func in HANDLERS:
                if pattern.match(mod_content):
                    func(mod_content)
                    break
            else:
                logger.warning("Unknown modifier '%s' in line: %s", mod_content, line)

        # Handle directory or specific image

        if path == "*":
            if state["group"]:
                self.defaults.groups[state["group"]] = {
                    "proportion": state["proportion"] or None,
                    "user_proportion": state["user_proportion"] or None,
                    "graft_level": state["graft_level"] or None,
                    "mode_modifier": state["mode_modifier"] or (),
                }
                return None, None
            if state["video"] is not None or state["mute"] is not None:
                self.defaults.set_global_video(video=state["video"], mute=state["mute"])
            if state["mode_modifier"]:
                self.detected_mode = state["mode_modifier"]
                self.detected_lowest = min(state["mode_modifier"].keys())
            if recdepth == 1 and apply_global_mode:
                self.defaults.set_global_defaults(
                    mode=state["mode_modifier"] or self.defaults.mode,
                    dont_recurse=state["dont_recurse"],
                )
            return None, None

        # Calculate an effective graft level when harmonising modes across inputs
        def _effective_graft_level(path_str: str) -> int | None:
            base_level = state["graft_level"]
            if base_level is None:
                parts = [p for p in os.path.normpath(path_str).split(os.path.sep) if p]
                base_level = len(parts)
            return base_level + graft_offset if graft_offset else base_level

        if os.path.isdir(path):
            return path, {
                "weight_modifier": state["weight_modifier"],
                "is_percentage": state["is_percentage"],
                "proportion": state["proportion"],
                "user_proportion": state["user_proportion"],
                "graft_level": _effective_graft_level(path),
                "group": state["group"],
                "mode_modifier": state["mode_modifier"],
                "flat": state["flat"],
                "video": state["video"],
            }
        elif os.path.isfile(path):
            return path, {
                "weight_modifier": state["weight_modifier"],
                "is_percentage": state["is_percentage"],
                "proportion": state["proportion"],
                "user_proportion": state["user_proportion"],
                "graft_level": _effective_graft_level(path),
                "group": state["group"],
                "mode_modifier": state["mode_modifier"],
            }
        else:
            logger.warning("Path '%s' is neither a file nor a directory.", path)

        return None, None
