import argparse
from enkan.config import add_config_arguments
from enkan.constants import VERSION


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
        "--config",
        type=str,
        default=None,
        help="Optional path to an app-level TOML config file",
    )
    parser.add_argument(
        "--outputlist", "--ol", nargs="?", const=True, metavar="FILE", help="Output lst slideshow file (optionally specify FILE) and exit"
    )
    parser.add_argument(
        "--outputtree", "--ot", nargs="?", const=True, metavar="FILE", help="Output tree binary file (optionally specify FILE) and exit"
    )
    parser.add_argument(
        "--run", dest="run", action="store_true", help="Run the slideshow"
    )
    parser.add_argument(
        "--test", metavar="N", type=int, help="Run the test with N iterations"
    )
    parser.add_argument(
        "--test_model",
        "--tm",
        type=str,
        default=None,
        help=(
            "Comma-separated image provider model suffixes to test, "
            "for example: weighted,controlled_random_weighted"
        ),
    )
    parser.add_argument(
        "--histo", action="store_true", help="Show distribution histogram"
    )
    parser.add_argument(
        "--no-recurse",
        "--nr",
        dest="no_recurse",
        action="store_true",
        help="Do not recurse through folder inputs while building txt/folder trees",
    )
    parser.add_argument(
        "--debug",
        type=int,
        choices=[1, 2, 3, 4, 5],
        default=2,
        help="Logging level: 5=hurt, 4=debug, 3=warn, 2=info (default), 1=error",
    )
    parser.add_argument(
        "--testdepth", type=int, default=None, help="Depth to display test results"
    )
    parser.add_argument(
        "--printtree", action="store_true", help="Print the tree structure"
    )
    add_config_arguments(parser)
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return parser
