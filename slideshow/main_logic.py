# ——— Standard library ———
import os

# ——— Local ———
from slideshow.utils.InputProcessor import InputProcessor
from slideshow.utils.Defaults import Defaults
from slideshow.utils.Filters import Filters
from slideshow.utils.tests import print_tree, test_distribution
from slideshow.tree.Tree import Tree
from slideshow.mySlideshow.start_slideshow import start_slideshow

def main(args):
    
    defaults = Defaults(args=args)
    filters = Filters()

    # Use args.input_file directly as a list
    input_files = args.input_file if args.input_file else []
    
    # Parse input files and directories
    processor = InputProcessor(defaults, filters, quiet=False)
    image_dirs, specific_images, all_images, weights = processor.process_inputs(input_files)

    if not any([image_dirs, specific_images, all_images, weights]):
        raise ValueError("No images found in the provided input files.")

    if image_dirs or specific_images:
        # Instantiate and build the tree
        tree = Tree(defaults, filters)
        tree.build_tree(image_dirs, specific_images)
        tree.calculate_weights()

        # Print tree if requested
        if args.printtree:
            print_tree(defaults, tree.root, max_depth=args.test or 9999)
            return

        # Extract paths and weights from the tree
        extracted_images, extracted_weights = (
            tree.extract_image_paths_and_weights_from_tree(args.test)
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
        test_distribution(all_images, weights, args.test, args.testdepth, defaults, args.quiet)
        return
    
    start_slideshow(all_images, weights, defaults)