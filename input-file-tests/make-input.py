import os
import argparse
import re
import tqdm

def find_exact_match(base_path, target_name):
    """Find a folder that exactly matches the target name (case insensitive)."""
    target_lower = target_name.lower()
    for folder in os.listdir(base_path):
        if os.path.isdir(os.path.join(base_path, folder)) and folder.lower() == target_lower:
            return folder
    return None

def find_folders_containing_name(base_path, target_name):
    """Find all folders that contain `[Name]` in their name within `base_path`, including inside base-name/[Name]."""
    pattern = re.compile(rf'(?<!\w){re.escape(target_name)}(?!\w)', re.IGNORECASE)
    matching_folders = set()
    
    for root, dirs, _ in tqdm.tqdm(os.walk(base_path), desc="Scanning folders", unit=" folder(s)"):
        for d in dirs:
            if pattern.search(d):
                matching_folders.add(os.path.join(root, d))
    
    return sorted(matching_folders)

def count_images_in_folder(folder_path):
    """Count image files in a folder."""
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}
    return sum(1 for f in os.listdir(folder_path) if os.path.splitext(f)[1].lower() in image_extensions)

def find_variations(base_set_path):
    """Find variations of a 'Set xxx' in the same directory and normalize them."""
    parent_dir = os.path.dirname(base_set_path)
    base_set_name = os.path.basename(base_set_path)
    
    variations = {}
    base_count = count_images_in_folder(base_set_path)
    if base_count > 0:
        variations[base_set_path] = base_count
    
    # Look for variations that start with the base name but have extra text at the end
    for folder in os.listdir(parent_dir):
        full_path = os.path.join(parent_dir, folder)
        if os.path.isdir(full_path) and folder.startswith(base_set_name) and folder != base_set_name:
            variant_count = count_images_in_folder(full_path)
            if variant_count > 0:
                variations[full_path] = variant_count
    
    total_images = sum(variations.values())
    if total_images > 0:
        for path in variations:
            variations[path] = round((variations[path] / total_images) * 100)
    return variations

def process_folders(base_path, target_name, base_model_path):
    """Find all folders containing `[Name]`, check for variations, and return results."""
    result_sets = {}
    written_paths = set()
    
    folders = find_folders_containing_name(base_path, target_name)
    for folder in tqdm.tqdm(folders, desc="Processing folders", unit=" folder(s)"):
        if folder not in written_paths:
            variations = find_variations(folder)
            if variations:
                result_sets[folder] = variations
            else:
                result_sets[folder] = {folder: None}  # Single folder without variations
            written_paths.add(folder)
    
    # Ensure variations inside base-name/[Name] are explicitly handled
    for root, dirs, _ in os.walk(base_model_path):
        for d in dirs:
            if re.search(r'\bSet \d+\b', d):
                set_path = os.path.join(root, d)
                if set_path not in written_paths:
                    variations = find_variations(set_path)
                    if variations:
                        result_sets[set_path] = variations
                    written_paths.add(set_path)
    
    return result_sets

def create_input_file(base_path, model_name, output_file, global_mode):
    if os.path.exists(output_file):
        confirm = input(f"File '{output_file}' already exists. Overwrite? (y/n): ")
        if confirm.lower() != 'y':
            print("Aborting.")
            return
    
    model_folder = find_exact_match(base_path, model_name)
    if not model_folder:
        print(f"Error: No exact match found for '{model_name}' in '{base_path}'")
        return
    
    model_folder_path = os.path.join(base_path, model_folder)
    folder_sets = process_folders(base_path, model_name, model_folder_path)
    
    # Avoid duplicate entries
    written_paths = set()
    
    with open(output_file, "w", encoding="utf-8") as f:
        if global_mode:
            f.write(f"[{global_mode}]*\n")
        
        if model_folder_path not in written_paths:
            f.write(f"{model_folder_path}\n")
            written_paths.add(model_folder_path)
        
        for set_path, variations in folder_sets.items():
            for variation_path, percentage in sorted(variations.items(), key=lambda x: -x[1] if x[1] is not None else 0):
                if variation_path not in written_paths:
                    if percentage is not None and percentage > 0:
                        f.write(f"[{percentage}%]{variation_path}\n")
                    else:
                        f.write(f"{variation_path}\n")  # No modifier for single entries
                    written_paths.add(variation_path)

def main():
    parser = argparse.ArgumentParser(description="Generate an input file for a specific model name.")
    parser.add_argument("-n", "--name", required=True, help="Model name to search for")
    parser.add_argument("-g", "--global_mode", help="Global mode string to add to the top of the file")
    args = parser.parse_args()
    
    base_path = "I:\\imagesftp\\!! model sets"
    output_file = f"{args.name.lower()}.txt"
    
    create_input_file(base_path, args.name, output_file, args.global_mode)
    print(f"Input file '{output_file}' created successfully.")

if __name__ == "__main__":
    main()