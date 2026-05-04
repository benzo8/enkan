# ——— Standard library ———
import os
import logging
from typing import List
from itertools import accumulate

# ——— Local ———
from enkan.config import load_app_config, merge_config_into_args, set_current_app_config
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
    app_config = load_app_config(getattr(args, "config", None))
    set_current_app_config(app_config)
    effective_args = merge_config_into_args(args, app_config)

    defaults: Defaults = Defaults(args=effective_args)
    set_current_defaults(defaults)
    filters: Filters = Filters()
    filters.preprocess_ignored_files()
    tree: Tree = None

    # Normalize input_files to list
    if not effective_args.input_file:
        input_files: List[str] = []
    elif isinstance(effective_args.input_file, str):
        input_files = [effective_args.input_file]
    else:
        input_files = list(effective_args.input_file)

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
    if effective_args.printtree:
        from enkan.tree.diagnostics import print_tree
        print_tree(defaults, tree.root, max_depth=effective_args.testdepth or 9999)
        return

    # Output tree to file if requested
    if effective_args.outputtree:
        from enkan.tree.tree_io import write_tree_to_file
        if isinstance(effective_args.outputtree, str):
            output_path = os.path.abspath(effective_args.outputtree)
        else:
            base_names = [os.path.splitext(os.path.basename(f))[0] for f in effective_args.input_file]
            output_name = "_".join(base_names) + ".tree"
            output_path = os.path.join(os.getcwd(), output_name)
        write_tree_to_file(tree, output_path)
        logger.info("Tree written to %s", output_path)
        return

    selection_scope = extract_selection_scope_from_tree(
        tree,
        test_iterations=effective_args.test,
    )
    images = selection_scope.image_paths
    weights = selection_scope.weights
        
    if effective_args.outputlist:
        from enkan.tree.tree_io import write_image_list
        # Build output filename
        if isinstance(effective_args.outputlist, str):
            output_path = os.path.abspath(effective_args.outputlist)
        else:
            base_names = [os.path.splitext(os.path.basename(f))[0] for f in effective_args.input_file]
            output_name = "_".join(base_names) + ".lst"
            output_path = os.path.join(os.getcwd(), output_name)
        write_image_list(images, weights, effective_args.input_file, effective_args.mode, output_path)
        logger.info("Output written to %s", output_path)
        return

    # Calcalate cumulative weights for slideshow
    cum_weights = list(accumulate(weights))

    # Test or start the slideshow
    if effective_args.test:
        from enkan.tree.diagnostics import test_distribution
        test_distribution(
            images,
            weights,
            cum_weights,
            effective_args.test,
            effective_args.testdepth,
            effective_args.histo,
            defaults,
            test_models=effective_args.test_model,
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
        effective_args.interval,
    )
