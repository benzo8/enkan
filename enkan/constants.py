import re
from importlib.metadata import version as _pkg_version, PackageNotFoundError

PACKAGE_NAME = "enkan"

try:
    VERSION = _pkg_version(PACKAGE_NAME)
except PackageNotFoundError:
    # Fallback during source-only situations (keep in sync with pyproject if used)
    VERSION = "2.0.1"
TOTAL_WEIGHT = 100
PARENT_STACK_MAX = 5
HISTORY_QUEUE_LENGTH = 25
CACHE_SIZE = 10
PRELOAD_QUEUE_LENGTH = 3
ROOT_NODE_NAME = "root"
IMAGE_FILES = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff")
VIDEO_FILES = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv")
TEXT_FILES = (".txt", ".lst")
CX_PATTERN = re.compile(r"^(?:[bw]\d+(?:,-?\d+)?(?:,-?\d+)?)+$", re.IGNORECASE)

MODIFIER_PATTERN = re.compile(r"(\[.*?\])")
WEIGHT_MODIFIER_PATTERN = re.compile(r"^\d+%?$")
PROPORTION_PATTERN = re.compile(r"^%\d+%?$")
MODE_PATTERN = CX_PATTERN
GRAFT_PATTERN = re.compile(r"^g\d+$", re.IGNORECASE)
GROUP_PATTERN = re.compile(r"^>.*", re.IGNORECASE)
FLAT_PATTERN = re.compile(r"^f$", re.IGNORECASE)
VIDEO_PATTERN = re.compile(r"^v$", re.IGNORECASE)
NO_VIDEO_PATTERN = re.compile(r"^nv$", re.IGNORECASE)
MUTE_PATTERN = re.compile(r"^m$", re.IGNORECASE)
NO_MUTE_PATTERN = re.compile(r"^nm$", re.IGNORECASE)
DONT_RECURSE_PATTERN = re.compile(r"^/$", re.IGNORECASE)
