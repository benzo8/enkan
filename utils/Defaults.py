import re

def parse_mode_string(mode_str):
    # Updated regex: ([bw])(\d+)(?:,(-?\d+))?(?:,(-?\d+))?
    pattern = re.compile(r"([bw])(\d+)(?:,(-?\d+))?(?:,(-?\d+))?", re.IGNORECASE)
    matches = pattern.findall(mode_str)
    # Each match is a tuple: (mode, level, slope1, slope2)
    # Convert level to int, slopes to int if present, else None
    result = {}
    for char, num, slope1, slope2 in matches:
        level = int(num)
        slopes = []
        if slope1:
            slopes.append(int(slope1))
        else:
            slopes.append(0)
        if slope2:
            slopes.append(int(slope2))
        else:
            slopes.append(0)
        result[level] = (char.lower(), slopes)
    return result

def resolve_mode(mode_dict, number):
    if not mode_dict:
        return ("w", [0, 0])  # Default to weighted mode, no slope

    first_key = min(mode_dict.keys())

    if number < first_key:
        return ("l", [0, 0])
    elif number in mode_dict:
        mode_info = mode_dict[number]
        if isinstance(mode_info, tuple):
            # (mode, slopes)
            mode, slope = mode_info
            # Ensure slopes is always a list of two ints
            if len(slope) == 1:
                slope = [slope[0], 0]
            elif len(slope) == 0:
                slope = [0, 0]
            return (mode, slope)
        else:
            # Backward compatibility: just a string
            return (mode_info, [0, 0])
    else:
        return ("w", [0, 0])


class Defaults:
    def __init__(
        self,
        weight_modifier=100,
        mode={1: "w"},
        depth=9999,
        is_random=False,
        args=None,
        groups={},
        video=True,
        mute=True,
    ):
        self.args = args
        self._weight_modifier = weight_modifier
        self._mode = mode
        self._depth = depth
        self._is_random = is_random
        self._video = video
        self._mute = mute

        self.global_mode = None
        self.global_depth = None
        self.global_is_random = None
        self.global_video = None
        self.global_mute = None

        self.args_mode = (
            parse_mode_string(args.mode) if args and args.mode is not None else None
        )
        self.args_depth = args.depth if args and args.depth is not None else None
        self.args_is_random = args.random if args and args.random is not None else None
        self.args_video = args.video if args and args.video is not None else None
        self.args_mute = args.mute if args and args.mute is not None else None

        self.groups = {}

    @property
    def weight_modifier(self):
        return self._weight_modifier

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
        if self.args_is_random is not None:
            return self.args_is_random
        elif self.global_is_random is not None:
            return self.global_is_random
        else:
            return self._is_random

    @property
    def video(self):
        if self.args_video is not None:  # CLI overrides all
            return self.args_video
        elif self.global_video is not None:  # folder-specific config
            return self.global_video
        else:
            return self._video  # built-in fallback

    @property
    def mute(self):
        if self.args_mute is not None:
            return self.args_mute
        elif self.global_mute is not None:
            return self.global_mute
        else:
            return self._mute

    def set_global_defaults(self, mode=None, depth=None, is_random=None):
        if mode is not None:
            self.global_mode = mode
        if depth is not None:
            self.global_depth = depth
        if is_random is not None:
            self.global_is_random = is_random

    def set_global_video(self, video=None, mute=None):
        if video is not None:
            self.global_video = video
        if mute is not None:
            self.global_mute = mute
