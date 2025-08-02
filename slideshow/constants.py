import re

# Constants
VERSION = "1.90-dev"
TOTAL_WEIGHT = 100
PARENT_STACK_MAX = 5
HISTORY_QUEUE_LENGTH = 25
CACHE_SIZE = 10
PRELOAD_QUEUE_LENGTH = 3
IMAGE_FILES = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff")
VIDEO_FILES = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv")
TEXT_FILES = (".txt", ".lst")
CX_PATTERN = re.compile(r"^(?:[bw]\d+(?:,-?\d+)?(?:,-?\d+)?)+$", re.IGNORECASE)