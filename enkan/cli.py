# ——— Standard library ———
import os
import logging
from typing import List
from itertools import accumulate

# ——— Local ———
from enkan.utils.InputProcessor import InputProcessor
from enkan.utils.Defaults import Defaults
from enkan.utils.Filters import Filters
from enkan.tree.tree_logic import (
    build_tree,
    extract_image_paths_and_weights_from_tree
)

logger = logging.getLogger("enkan.main")  

def main_with_args(args) -> None:
    
    defaults: Defaults = Defaults(args=args)
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

    processor = InputProcessor(defaults, filters, args.quiet or False)
    tree, image_dirs, specific_images, all_images, weights = processor.process_inputs(input_files)

    if not any([tree, image_dirs, specific_images, all_images, weights]):
        raise ValueError("No images found in the provided input files.")

    if image_dirs or specific_images or tree:
        # Instantiate and build the tree
        if not tree:
            tree = build_tree(defaults, filters, image_dirs, specific_images, quiet=False)

        # Print tree if requested
        if args.printtree:
            from enkan.utils.tests import print_tree
            print_tree(defaults, tree.root, max_depth=args.testdepth or 9999)
            return

        if args.outputtree:
            from enkan.utils.utils import write_tree_to_file
            base_names = [os.path.splitext(os.path.basename(f))[0] for f in args.input_file]
            output_name = "_".join(base_names) + ".tree"
            output_path = os.path.join(os.getcwd(), output_name)
            write_tree_to_file(tree, output_path)
            logger.info("Tree written to %s", output_path)
            return

        # Extract paths and weights from the tree
        extracted_images, extracted_weights = (
            extract_image_paths_and_weights_from_tree(tree, test_iterations=args.test)
        ) 
        all_images.extend(extracted_images)
        weights.extend(extracted_weights)
        
    cum_weights = list(accumulate(weights))

    if args.outputlist:
        from enkan.utils.utils import write_image_list
        # Build output filename
        base_names = [os.path.splitext(os.path.basename(f))[0] for f in args.input_file]
        output_name = "_".join(base_names) + ".lst"
        output_path = os.path.join(os.getcwd(), output_name)
        write_image_list(all_images, weights, args.input_file, args.mode, output_path)
        logger.info("Output written to %s", output_path)
        return

    # Test or start the slideshow
    if args.test:
        from enkan.utils.tests import test_distribution
        test_distribution(all_images, cum_weights, args.test, args.testdepth, args.histo, defaults, args.quiet or False)
        return
    
    from enkan.mySlideshow.start_slideshow import start_slideshow
    if not tree:
        from enkan.tree.Tree import Tree
        tree = Tree(defaults, filters)
    start_slideshow(tree, all_images, cum_weights, defaults, filters, args.quiet or False, args.interval)