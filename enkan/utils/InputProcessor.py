import os
from typing import Dict, List, Any
import logging
from tqdm import tqdm

from enkan import constants
from enkan.tree.Tree import Tree
from enkan.utils import utils
from enkan.utils.Defaults import parse_mode_string

logger: logging.Logger = logging.getLogger(__name__)

class InputProcessor:
    def __init__(self, defaults, filters, quiet=False):
        self.defaults = defaults
        self.filters = filters
        self.quiet = quiet

    def process_inputs(self, input_files, recdepth=1):
        """
        Parse input files and directories to create image_dirs and specific_images dictionaries.

        Args:
            input_files (list): List of input files or directories.
            defaults (object): Defaults object containing configuration.

        Returns:
            tuple: (image_dirs, specific_images)
        """
        image_dirs: Dict = {}
        specific_images: Dict = {}
        all_images: List = []
        weights: List = []

        for input_entry in input_files:
            tree: Tree = self.process_entry(
                input_entry, recdepth, image_dirs, specific_images, all_images, weights
            )
            if tree:
                return tree, {}, {}, [], []
        return None, image_dirs, specific_images, all_images, weights

    def _load_tree_if_current(self, filename: str) -> Tree | None:
        """
        Attempt to load a pickled Tree; return None if version missing/outdated.
        """
        from enkan.utils.utils import load_tree_from_file
        try:
            tree = load_tree_from_file(filename)
        except Exception as e:
            logger.warning("[tree] Failed to load '%s': %s.", filename, e)
            return None
        version_in_pickle = getattr(tree, "_pickle_version", None)
        if version_in_pickle is None or version_in_pickle < Tree.PICKLE_VERSION:
            tree_filename = os.path.basename(filename)
            txt_filename = os.path.splitext(tree_filename)[0] + ".txt"
            logger.info(
                "[tree] '%s' outdated (pickle_version=%d, required=%d).\n"
                "Please rebuild with: enkan --input_file %s --outputtree",
                tree_filename,
                version_in_pickle,
                Tree.PICKLE_VERSION,
                txt_filename,
            )
            return None
        return tree

    def process_entry(
        self, entry, recdepth, image_dirs, specific_images, all_images, weights
    ) -> Tree | None:
        """
        Process a single input entry (file, directory, or image).
        """

        additional_search_paths = [os.path.dirname(entry)]
        input_filename_full = utils.find_input_file(entry, additional_search_paths)

        if input_filename_full:
            match os.path.splitext(input_filename_full)[1].lower():
                case ".tree":
                    # Load a pre-built tree from a file
                    tree = self._load_tree_if_current(input_filename_full)
                    if tree:
                        logger.info("Loaded current tree from %s", input_filename_full)
                        return tree
                    stem = os.path.splitext(input_filename_full)[0]
                    for ext in (".lst", ".txt"):
                        alt = stem + ext
                        if os.path.isfile(alt):
                            # Reinvoke processing on the alternate file
                            return self.process_entry(
                                alt, recdepth, image_dirs, specific_images, all_images, weights
                            )
                    # If no alternate source list, just stop (nothing else to parse here)
                    return None                
                case ".lst":
                    with open(
                        input_filename_full, "r", buffering=65536, encoding="utf-8"
                    ) as f:
                        total_lines = sum(1 for _ in f)
                        f.seek(0)
                        for line in tqdm(
                            f,
                            desc=f"Parsing {input_filename_full}",
                            unit="line",
                            total=total_lines,
                            disable=self.quiet,
                        ):
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            image_path, weight_str = line.rsplit(
                                ",", 1
                            )  # Split on last comma
                            if weight_str:  # Expecting "image_path,weight"
                                try:
                                    weights.append(float(weight_str))
                                    all_images.append(image_path)
                                except ValueError:
                                    # weight_str is not a number, so it's part of the image path (comma in filename)
                                    all_images.append(f"{image_path},{weight_str}")
                                    weights.append(
                                        0.01
                                    )  # Default weight for single lines
                            else:  # Probably an irfanview-style list
                                all_images.append(line)
                                weights.append(0.01)  # Default weight for single lines
                    logger.info("Loaded slide list from %s", input_filename_full)
                case ".txt":
                    with open(
                        input_filename_full, "r", buffering=65536, encoding="utf-8"
                    ) as f:
                        total_lines = sum(1 for _ in f)
                        f.seek(0)
                        for line in tqdm(
                            f,
                            desc=f"Parsing {input_filename_full}",
                            unit="line",
                            total=total_lines,
                            disable=self.quiet,
                        ):
                            line = line.strip()
                            if not line or line.startswith(
                                "#"
                            ):  # Skip comments/empty lines
                                continue
                            line = line.replace(
                                '"', ""
                            ).strip()  # Remove enclosing quotes

                            if utils.is_textfile(
                                line
                            ):  # Recursively process nested text files
                                sub_image_dirs, sub_specific_images, _, _ = (
                                    self.process_inputs([line], recdepth + 1)
                                )
                                image_dirs.update(sub_image_dirs)
                                specific_images.update(sub_specific_images)
                            else:
                                path, modifier_list = self.parse_input_line(
                                    line, recdepth
                                )
                                if modifier_list:
                                    if utils.is_imagefile(path):
                                        specific_images[path] = modifier_list
                                    else:
                                        image_dirs[path] = modifier_list
        else:  # Handle directories and images directly
            path, modifier_list = self.parse_input_line(entry, recdepth)
            if modifier_list:
                if utils.is_imagefile(path):
                    specific_images[path] = modifier_list
                else:
                    image_dirs[path] = modifier_list

    def parse_input_line(self, line, recdepth):


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
            "is_percentage": True,
            "graft_level": None,
            "group": None,
            "mode_modifier": None,
            "flat": False,
            "video": None,
            "mute": None,
            "dont_recurse": None,
            "ignore_below_bottom": False,
        }
        base_mode = self.defaults.mode
        
        def handle_weight(s: str):
            if s.endswith("%"):
                state["weight_modifier"] = int(s[:-1])
                state["is_percentage"] = True
            else:
                state["weight_modifier"] = int(s)
                state["is_percentage"] = False

        def handle_proportion(s: str):
            # strip leading/trailing %: e.g. %33% or %10
            state["proportion"] = int(s.strip("%"))

        def handle_graft(s: str):
            state["graft_level"] = int(s[1:])

        def handle_group(s: str):
            state["group"] = s[1:]

        def handle_mode(s: str):
            state["mode_modifier"] = parse_mode_string(s)

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

        def handle_ignore_below_bottom(_s: str):
            state["ignore_below_bottom"] = True

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
            (constants.IGNORE_BELOW_BOTTOM_PATTERN, handle_ignore_below_bottom),
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
                    "graft_level": state["graft_level"] or None,
                    "mode_modifier": state["mode_modifier"] or (),
                }
                return None, None
            if state["video"] is not None or state["mute"] is not None:
                self.defaults.set_global_video(video=state["video"], mute=state["mute"])
            if recdepth == 1:
                self.defaults.set_global_defaults(mode=state["mode_modifier"] or base_mode, dont_recurse=state["dont_recurse"])
            if state["ignore_below_bottom"]:
                self.filters.configure_ignore_below_bottom(True, self.defaults.mode)
            return None, None

        if os.path.isdir(path):
            return path, {
                "weight_modifier": state["weight_modifier"],
                "is_percentage": state["is_percentage"],
                "proportion": state["proportion"],
                "graft_level": state["graft_level"],
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
                "graft_level": state["graft_level"],
                "group": state["group"],
                "mode_modifier": state["mode_modifier"],
            }
        else:
            logger.warning("Path '%s' is neither a file nor a directory.", path)

        return None, None
