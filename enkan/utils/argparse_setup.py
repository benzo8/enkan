import argparse
from enkan.constants import CX_PATTERN, VERSION


# Argument parsing setup
def cx_type(s: str) -> str:
    """
    argparse “type” function: returns the string if it matches,
    otherwise raises ArgumentTypeError.
    """
    if not CX_PATTERN.fullmatch(s):
        msg = (
            f"invalid Cx string {s!r}; "
            "must be one or more blocks of B or W followed by digits (case-insensitive), "
            "e.g. B1, W23, B1W2B300"
        )
        raise argparse.ArgumentTypeError(msg)
    return s.lower()


def get_arg_parser() -> argparse.ArgumentParser:
    """
    Create and return the argument parser for the slideshow application.
    """
    parser = argparse.ArgumentParser(
        description="Create a slideshow from a list of files."
    )
    parser.add_argument(
        "--input_file",
        "-i",
        metavar="input_file",
        nargs="+",
        type=str,
        help="Input file(s) and/or folder(s) to build or .lst file to load",
    )
    parser.add_argument(
        "--outputlist", "--ol", action="store_true", help="Output lst slideshow file and exit"
    )
    parser.add_argument(
        "--outputtree", "--ot", action="store_true", help="Output tree binary file and exit"
    )
    parser.add_argument(
        "--run", dest="run", action="store_true", help="Run the slideshow"
    )
    parser.add_argument(
        "-m-",
        "--mode",
        type=cx_type,
        help="Mode string. One or more occurrences of B or W (case-insensitive) followed by digits, e.g. B12W3",
    )
    parser.add_argument(
        "--random", action="store_true", help="Start in Completely Random mode"
    )
    parser.add_argument(
        "--auto",
        "-a",
        type=int,
        dest="interval",
        default=0,
        help="Time in seconds for automated slide changes",
    )
    parser.add_argument(
        "--no-recurse",
        "--nr",
        dest="dont_recurse",
        action="store_true",
        help="Do not recurse through folders",
    )
    parser.set_defaults(dont_recurse=None)
    parser.add_argument(
        "--ignore-below-bottom",
        "--ibb",
        action="store_true",
        help="Ignore images in folders below the first mode rung",
    )
    parser.add_argument(
        "--video", dest="video", action="store_true", help="Enable video playback"
    )
    parser.add_argument(
        "--no-video",
        "--nv",
        dest="video",
        action="store_false",
        help="Disable video playback",
    )
    parser.set_defaults(video=None)
    parser.add_argument(
        "--no-mute", "--nm", dest="mute", action="store_false", help="Disable mute"
    )
    parser.set_defaults(mute=None)
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Run in quiet mode (no output)"
    )
    parser.add_argument(
        "--no-background", "--nbg", action="store_true", help="Force queue/cache loading into foreground"
    )
    parser.set_defaults(no_background=False)
    parser.add_argument(
        "--test", metavar="N", type=int, help="Run the test with N iterations"
    )
    parser.add_argument(
        "--histo", action="store_true", help="Show distribution histogram"
    )
    parser.add_argument(
        "--debug", action="store_true"
    )
    parser.add_argument(
        "--testdepth", type=int, default=None, help="Depth to display test results"
    )
    parser.add_argument(
        "--printtree", action="store_true", help="Print the tree structure"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return parser
