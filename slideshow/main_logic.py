# ——— Standard library ———
import os

# ——— Local ———
from slideshow.utils.InputProcessor import InputProcessor
from slideshow.utils.Defaults import Defaults
from slideshow.utils.Filters import Filters
from slideshow.tree.tree_logic import (
    build_tree,
    extract_image_paths_and_weights_from_tree
)


def main(args):
    
    defaults = Defaults(args=args)
    filters = Filters()
    filters.preprocess_ignored_files()

    # Use args.input_file directly as a list
    input_files = args.input_file if args.input_file else []
    
    # Parse input files and directories
    processor = InputProcessor(defaults, filters, args.quiet or False)
    image_dirs, specific_images, all_images, weights = processor.process_inputs(input_files)

    if not any([image_dirs, specific_images, all_images, weights]):
        raise ValueError("No images found in the provided input files.")

    if image_dirs or specific_images:
        # Instantiate and build the tree
        tree = build_tree(defaults, filters, image_dirs, specific_images, quiet=False)

        # Print tree if requested
        if args.printtree:
            from slideshow.utils.tests import print_tree
            print_tree(defaults, tree.root, max_depth=args.testdepth or 9999)
            return

        # Extract paths and weights from the tree
        extracted_images, extracted_weights = (
            extract_image_paths_and_weights_from_tree(tree, args.test)
        ) 
        all_images.extend(extracted_images)
        weights.extend(extracted_weights)

    if args.output:
        from slideshow.utils.utils import write_image_list
        # Build output filename
        base_names = [os.path.splitext(os.path.basename(f))[0] for f in args.input_file]
        output_name = "_".join(base_names) + ".lst"
        output_path = os.path.join(os.getcwd(), output_name)
        write_image_list(all_images, weights, args.input_file, args.mode, output_path)
        print(f"Output written to {output_path}")
        return

    # Test or start the slideshow
    if args.test:
        from slideshow.utils.tests import test_distribution
        test_distribution(all_images, weights, args.test, args.testdepth, defaults, args.quiet or False)
        return
    
    from slideshow.mySlideshow.start_slideshow import start_slideshow
    start_slideshow(tree, all_images, weights, defaults, filters, args.quiet or False, args.interval)