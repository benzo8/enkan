import os
from typing import Dict, List, Any, Optional
import logging


from enkan import constants
from enkan.tree.Tree import Tree
from enkan.utils import utils
from enkan.utils.Mode import Mode
from enkan.utils.progress import progress

logger: logging.Logger = logging.getLogger(__name__)


class InputProcessor:
    def __init__(self, build_state, build_filters):
        self.build_state = build_state
        self.build_filters = build_filters
        self.detected_mode = None
        self.detected_lowest = None

    def process_input(
        self,
        input_entry,
        recdepth: int = 1,
        graft_offset: int = 0,
        apply_global_mode: bool = True,
        nested_paths: Optional[List[str]] = None,
    ):
        """
        Parse a .txt entry into image_dirs/specific_images structures.
        Returns (image_dirs, specific_images).
        """
        image_dirs: Dict = {}
        specific_images: Dict = {}
        # reset detected mode for this run
        self.detected_mode = None
        self.detected_lowest = None

        self._process_entry(
            entry=input_entry,
            recdepth=recdepth,
            image_dirs=image_dirs,
            specific_images=specific_images,
            graft_offset=graft_offset,
            apply_global_mode=apply_global_mode,
            nested_paths=nested_paths,
        )
        return image_dirs, specific_images

    def _process_entry(
        self,
        entry,
        recdepth,
        image_dirs,
        specific_images,
        graft_offset: int = 0,
        apply_global_mode: bool = True,
        nested_paths: Optional[List[str]] = None,
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
                # Surface nested references upward for MSB to handle
                if nested_paths is not None and ext in {".lst", ".tree", ".txt"}:
                    nested_paths.append(input_filename_full)
                else:
                    logger.warning(
                        "Skipping non-txt input '%s' in InputProcessor.",
                        input_filename_full,
                    )
                return None
            with open(input_filename_full, "r", buffering=65536, encoding="utf-8") as f:
                total_lines = sum(1 for _ in f)
                f.seek(0)
                for line in progress(
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
                    if line_ext in {".txt", ".lst", ".tree"}:
                        if nested_paths is not None:
                            nested_ref = constants.MODIFIER_PATTERN.sub("", line).strip()
                            if nested_ref != line:
                                logger.warning(
                                    "Ignoring modifiers on nested input reference '%s'.",
                                    line,
                                )
                            resolved_nested = utils.find_input_file(
                                nested_ref,
                                [os.path.dirname(input_filename_full)],
                            )
                            if not resolved_nested and not os.path.isabs(nested_ref):
                                resolved_nested = os.path.normpath(
                                    os.path.join(
                                        os.path.dirname(input_filename_full),
                                        nested_ref,
                                    )
                                )
                            nested_paths.append(resolved_nested or nested_ref)
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
            logger.warning(
                "Ignoring legacy [r] input modifier; use slideshow.provider = "
                '"random" or --random instead.'
            )
            return None, None

        # Handle filters
        if line.startswith("[+]"):
            keyword: str = line[3:].strip()
            self.build_filters.add_must_contain(keyword)
            return None, None
        elif line.startswith("[-]"):
            path_or_keyword: str = line[3:].strip()
            if os.path.isabs(path_or_keyword):
                if os.path.isfile(path_or_keyword):
                    self.build_filters.add_ignored_file(path_or_keyword)
                else:
                    self.build_filters.add_ignored_dir(path_or_keyword)
            else:
                self.build_filters.add_must_not_contain(path_or_keyword)
            return None, None

        # Strip quotes early (if users quote paths)
        line = line.replace('"', "").strip()

        # Extract all modifiers
        modifiers = constants.MODIFIER_PATTERN.findall(line)
        # Remove all modifiers from the line to get the path
        path = constants.MODIFIER_PATTERN.sub("", line).strip()

        # Per-line state container (handlers mutate this)
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
            logger.warning(
                "Ignoring deprecated [m] input modifier; use slideshow.mute "
                "or --no-mute for runtime mute defaults."
            )

        def handle_no_mute(_s: str):
            state["mute"] = False
            logger.warning(
                "Ignoring deprecated [nm] input modifier; use slideshow.mute "
                "or --no-mute for runtime mute defaults."
            )

        def handle_dont_recurse(_s: str):
            state["dont_recurse"] = True
            self.build_filters.add_dont_recurse_beyond_folder(path)

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
                self.build_state.groups[state["group"]] = {
                    "proportion": state["proportion"] or None,
                    "user_proportion": state["user_proportion"] or None,
                    "graft_level": state["graft_level"] or None,
                    "mode_modifier": state["mode_modifier"] or (),
                }
                return None, None
            if state["video"] is not None:
                self.build_filters.include_video = state["video"]
            if state["mode_modifier"]:
                self.detected_mode = state["mode_modifier"]
                self.detected_lowest = min(state["mode_modifier"].keys())
            if recdepth == 1 and apply_global_mode:
                self.build_state.set_mode(
                    state["mode_modifier"] or self.build_state.mode
                )
                if state["dont_recurse"] is not None:
                    self.build_filters.dont_recurse = state["dont_recurse"]
            return None, None

        # Calculate an effective graft level when harmonising modes across inputs
        def _effective_graft_level(path_str: str) -> int | None:
            group_config = (
                self.build_state.groups.get(state["group"]) if state["group"] else None
            )
            group_graft_level = (
                group_config.get("graft_level") if group_config else None
            )
            if state["graft_level"] is not None:
                base_level = state["graft_level"]
            elif group_graft_level is not None:
                base_level = group_graft_level
            else:
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
