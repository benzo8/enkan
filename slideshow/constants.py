import re

# Constants
VERSION = "1.41-main"
TOTAL_WEIGHT = 100
PARENT_STACK_MAX = 5
QUEUE_LENGTH_MAX = 25
IMAGE_FILES = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff")
VIDEO_FILES = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv")
TEXT_FILES = (".txt", ".lst")
CX_PATTERN = re.compile(r"^(?:[bw]\d+(?:,-?\d+)?(?:,-?\d+)?)+$", re.IGNORECASE)