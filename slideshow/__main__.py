# -----------------------------------------------------------------------------
# slideshow-new.py
#
# A Python script to create a slideshow from a list of files, with various
# modes and features including weighted, balanced, and random selection.
#
# Author:      John Sullivan
# Created:     2023-2025
# License:     MIT License
# Copyright:   (c) 2023-2025 John Sullivan
#
# Description:
#   This script builds a slideshow from directories or lists of images,
#   supporting advanced weighting, folder balancing, and navigation features.
#   It uses Tkinter for the GUI and Pillow for image handling.
#
# Usage:
#   python slideshow-new.py --input_file <file_or_folder> [options]
# 
# Dependencies:
#   - Python 3.8+
#   - Pillow
#   - tqdm
#
# -----------------------------------------------------------------------------

from slideshow.utils.argparse_setup import get_arg_parser
from slideshow.main_logic import main_with_args

def main() -> None:
    """Console script / module entry point."""
    args = get_arg_parser().parse_args()
    main_with_args(args)


if __name__ == "__main__":
    main()