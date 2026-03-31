# -----------------------------------------------------------------------------
# # A Python script to create a slideshow from a list of files, with various
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
#   enkan --input_file <file_or_folder> [options]
# 
# Dependencies:
#   - Python 3.8+
#   - Pillow
#   - tqdm
#
# -----------------------------------------------------------------------------

import logging
from enkan.utils.argparse_setup import get_arg_parser
from enkan.utils.logging import configure_logging
from enkan.cli import main_with_args

def main() -> None:
    """Console script / module entry point."""
    args = get_arg_parser().parse_args()
    configure_logging(log_level=getattr(args, "debug", 2))
    try:
        main_with_args(args)
    except Exception as e:
        logging.getLogger("enkan").error("Fatal: %s", e)
        # No traceback shown unless debug enabled
        if getattr(args, "debug", 0) >= 4:
            raise

if __name__ == "__main__":
    main()
