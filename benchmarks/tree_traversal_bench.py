#!/usr/bin/env python
"""Benchmark TreeBuilder traversal strategies."""

import argparse
import csv
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Dict, Iterable, List, Mapping, Optional

from enkan.tree.Tree import Tree
from enkan.tree.TreeBuilderTXT import TreeBuilder
from enkan.utils.Defaults import Defaults
from enkan.utils.Filters import Filters
from enkan.utils.input.InputProcessor import InputProcessor


@dataclass
class RunResult:
    run_index: int
    strategy: str
    duration_s: float
    branches: int
    images: int
    nodes: int


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare os.walk and os.scandir traversal performance."
    )
    parser.add_argument(
        "-i",
        "--input",
        action="append",
        default=[],
        help="Input file or directory (repeatable, mirrors CLI expectations).",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=5,
        help="Number of measured iterations per strategy (default: 5).",
    )
    parser.add_argument(
        "--warmups",
        type=int,
        default=0,
        help="Warm-up passes per strategy executed before timing (default: 0).",
    )
    parser.add_argument(
        "--alternate",
        action="store_true",
        help="Alternate strategies each cycle instead of grouping runs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional CSV file to store per-run results.",
    )
    parser.add_argument(
        "--show-progress",
        action="store_true",
        help="Enable TreeBuilder progress bars (disabled by default).",
    )
    parser.add_argument(
        "--clear-standby",
        action="store_true",
        help="Clear Windows standby list using EmptyStandbyList.exe before each run (requires admin privileges).",
    )
    parser.add_argument(
        "--standby-exe",
        type=Path,
        help="Override path to EmptyStandbyList.exe (defaults to benchmarks directory).",
    )
    parser.add_argument(
        "--label",
        help="Optional label included in console output for bookkeeping.",
    )
    return parser.parse_args()


def prepare_inputs(args: argparse.Namespace) -> tuple[Defaults, Filters, Mapping[str, Dict[str, object]], Optional[Mapping[str, Dict[str, object]]]]:
    if not args.input:
        raise SystemExit("At least one --input is required.")

    defaults_stub = argparse.Namespace(
        mode=None,
        random=None,
        dont_recurse=None,
        video=None,
        mute=None,
        debug=False,
        no_background=False,
    )
    defaults = Defaults(args=defaults_stub)
    filters = Filters()

    processor = InputProcessor(defaults, filters)
    tree, image_dirs, specific_images, _, _ = processor.process_inputs(args.input)

    if tree is not None:
        raise SystemExit("Benchmark expects raw directories, not a pre-built tree file.")

    if not image_dirs and not specific_images:
        raise SystemExit("No usable image directories resolved from inputs.")

    filters.preprocess_ignored_files()
    return defaults, filters, image_dirs, specific_images or None




def _ensure_windows() -> None:
    if sys.platform != "win32":
        raise SystemExit("Clearing the Windows standby list is only supported on Windows hosts.")


def resolve_standby_executable(clear_requested: bool, override: Optional[Path]) -> Optional[Path]:
    if not clear_requested:
        return None
    _ensure_windows()
    executable = override.expanduser().resolve() if override is not None else Path(__file__).resolve().with_name("EmptyStandbyList.exe")
    if not executable.exists():
        raise SystemExit(f"Requested standby list clearing but '{executable}' was not found.")
    if not executable.is_file():
        raise SystemExit(f"Standby list helper '{executable}' is not a file.")
    return executable


def clear_standby_list(executable: Path) -> None:
    _ensure_windows()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.run(
            [str(executable), "standbylist"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creationflags,
        )
    except PermissionError as exc:
        raise SystemExit("Permission denied while clearing standby list. Run this script from an elevated Administrator prompt.") from exc
    except FileNotFoundError as exc:
        raise SystemExit(f"Failed to execute standby helper at '{executable}'.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        message = f"Standby list clearing failed with exit code {exc.returncode}."
        if stderr:
            message += f" Details: {stderr}"
        message += " Ensure the script is run with administrative privileges."
        raise SystemExit(message) from exc


def run_builder(
    strategy: str,
    run_index: int,
    defaults: Defaults,
    filters: Filters,
    image_dirs: Mapping[str, Dict[str, object]],
    specific_images: Optional[Mapping[str, Dict[str, object]]],
) -> RunResult:
    tree = Tree(defaults, filters)
    builder = TreeBuilder(tree)
    start = perf_counter()
    try:
        builder.build_tree(
            image_dirs,
            specific_images,
            traversal=strategy,
        )
    except TypeError as exc:
        if "traversal" not in str(exc):
            raise
        builder.build_tree(
            image_dirs,
            specific_images,
        )
    duration = perf_counter() - start
    branches, images = tree.count_branches(tree.root)
    node_count = len(tree.node_lookup)
    return RunResult(run_index, strategy, duration, branches, images, node_count)


def warm_up(
    count: int,
    defaults: Defaults,
    filters: Filters,
    image_dirs: Mapping[str, Dict[str, object]],
    specific_images: Optional[Mapping[str, Dict[str, object]]],
    standby_executable: Optional[Path],
) -> None:
    if count <= 0:
        return
    for strategy in ("walk", "scandir"):
        for _ in range(count):
            if standby_executable is not None:
                clear_standby_list(standby_executable)
            run_builder(strategy, 0, defaults, filters, image_dirs, specific_images)


def build_sequence(cycles: int, alternate: bool) -> List[str]:
    cycles = max(1, cycles)
    if not alternate:
        return ["walk"] * cycles + ["scandir"] * cycles

    sequence: List[str] = []
    for index in range(cycles):
        if index % 2 == 0:
            sequence.extend(["walk", "scandir"])
        else:
            sequence.extend(["scandir", "walk"])
    return sequence


def summarise(results: Iterable[RunResult]) -> Dict[str, Dict[str, float]]:
    grouped: Dict[str, List[float]] = {"walk": [], "scandir": []}
    for item in results:
        grouped.setdefault(item.strategy, []).append(item.duration_s)

    summary: Dict[str, Dict[str, float]] = {}
    for strategy, durations in grouped.items():
        if not durations:
            continue
        stats: Dict[str, float] = {
            "mean": statistics.mean(durations),
            "min": min(durations),
            "max": max(durations),
        }
        if len(durations) > 1:
            stats["stdev"] = statistics.stdev(durations)
        summary[strategy] = stats
    return summary


def write_csv(path: Path, results: Iterable[RunResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "run_index",
        "strategy",
        "duration_s",
        "branches",
        "images",
        "nodes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in results:
            writer.writerow(
                {
                    "run_index": item.run_index,
                    "strategy": item.strategy,
                    "duration_s": f"{item.duration_s:.6f}",
                    "branches": item.branches,
                    "images": item.images,
                    "nodes": item.nodes,
                }
            )


def main() -> None:
    args = parse_arguments()
    defaults, filters, image_dirs, specific_images = prepare_inputs(args)

    standby_executable = resolve_standby_executable(args.clear_standby, args.standby_exe)

    warm_up(args.warmups, defaults, filters, image_dirs, specific_images, standby_executable)

    sequence = build_sequence(args.cycles, args.alternate)
    total_runs = len(sequence)
    results: List[RunResult] = []
    for index, strategy in enumerate(sequence, start=1):
        print(f"Test {index} of {total_runs} ({strategy})", flush=True)
        if standby_executable is not None:
            clear_standby_list(standby_executable)
        result = run_builder(
            strategy,
            index,
            defaults,
            filters,
            image_dirs,
            specific_images,
        )
        results.append(result)

    summary = summarise(results)

    if args.output:
        write_csv(args.output, results)

    if args.label:
        print(f"Label: {args.label}")

    print("Run  Strategy  Duration(s)  Branches  Images  Nodes")
    for item in results:
        print(
            f"{item.run_index:>3}  {item.strategy:>8}  {item.duration_s:>11.6f}"
            f"  {item.branches:>8}  {item.images:>6}  {item.nodes:>5}"
        )

    print()
    for strategy in ("walk", "scandir"):
        stats = summary.get(strategy)
        if not stats:
            continue
        stdev = stats.get("stdev")
        part = (
            f"mean={stats['mean']:.6f}s, min={stats['min']:.6f}s, max={stats['max']:.6f}s"
        )
        if stdev is not None:
            part += f", stdev={stdev:.6f}s"
        print(f"{strategy}: {part}")

    walk_stats = summary.get("walk")
    scandir_stats = summary.get("scandir")
    if walk_stats and scandir_stats:
        delta = scandir_stats["mean"] - walk_stats["mean"]
        print(f"Delta (scandir - walk): {delta:.6f}s")


if __name__ == "__main__":
    main()
