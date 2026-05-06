# ——— Standard library ———
import os
import logging
from typing import List
from itertools import accumulate

# ——— Local ———
from enkan.config import Config
from enkan.tree.Tree import Tree
from enkan.tree.tree_logic import (
    extract_selection_scope_from_tree,
)
from enkan.utils.Defaults import Defaults, set_current_defaults
from enkan.utils.Filters import Filters
from enkan.utils.SelectionWeights import SelectionWeights
from enkan.utils.input.MultiSourceBuilder import MultiSourceBuilder

logger = logging.getLogger("enkan.main")  

def main_with_args(args) -> None:
    config = Config.from_args(args)

    defaults: Defaults = Defaults(args=args, config=config)
    set_current_defaults(defaults)
    filters: Filters = Filters()
    filters.preprocess_ignored_files()
    tree: Tree = None

    # Normalize input_files to list
    if not args.input_file:
        input_files: List[str] = []
    elif isinstance(args.input_file, str):
        input_files = [args.input_file]
    else:
        input_files = list(args.input_file)

    # Build the tree from multiple sources
    builder = MultiSourceBuilder(defaults, filters)
    tree, merge_warnings = builder.build(input_files)
    if merge_warnings:
        for msg in merge_warnings:
            logger.warning(msg)
    if tree is None:
        logger.error(
            "No tree could be built from the provided inputs; check that sources exist."
        )
        return

    # Print tree if requested
    if args.printtree:
        from enkan.tree.diagnostics import print_tree
        print_tree(defaults, tree.root, max_depth=args.testdepth or 9999)
        return

    # Output tree to file if requested
    if args.outputtree:
        from enkan.tree.tree_io import write_tree_to_file
        if isinstance(args.outputtree, str):
            output_path = os.path.abspath(args.outputtree)
        else:
            base_names = [os.path.splitext(os.path.basename(f))[0] for f in args.input_file]
            output_name = "_".join(base_names) + ".tree"
            output_path = os.path.join(os.getcwd(), output_name)
        write_tree_to_file(tree, output_path)
        logger.info("Tree written to %s", output_path)
        return

    selection_scope = extract_selection_scope_from_tree(
        tree,
        test_iterations=args.test,
    )
    images = selection_scope.image_paths
    weights = selection_scope.weights
        
    if args.outputlist:
        from enkan.tree.tree_io import write_image_list
        # Build output filename
        if isinstance(args.outputlist, str):
            output_path = os.path.abspath(args.outputlist)
        else:
            base_names = [os.path.splitext(os.path.basename(f))[0] for f in args.input_file]
            output_name = "_".join(base_names) + ".lst"
            output_path = os.path.join(os.getcwd(), output_name)
        write_image_list(
            images,
            weights,
            args.input_file,
            config("slideshow.mode"),
            output_path,
        )
        logger.info("Output written to %s", output_path)
        return

    # Calcalate cumulative weights for slideshow
    cum_weights = list(accumulate(weights))

    # Test or start the slideshow
    if args.test:
        from enkan.tree.diagnostics import test_distribution
        test_distribution(
            images,
            weights,
            cum_weights,
            args.test,
            args.testdepth,
            args.histo,
            defaults,
            test_models=args.test_model,
        )
        return
    
    from enkan.mySlideshow.start_slideshow import start_slideshow
    start_slideshow(
        tree,
        images,
        SelectionWeights.from_parts(weights, cum_weights),
        selection_scope,
        defaults,
        filters,
        config,
    )
