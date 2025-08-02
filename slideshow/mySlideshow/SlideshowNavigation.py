import os
from slideshow.utils.utils import level_of, truncate_path
from slideshow.tree.tree_logic import (
    build_tree, 
    extract_image_paths_and_weights_from_tree
)

class SlideshowNavigation:
    def __init__(self, states, update_display_callback):
        self.subfolder_mode = states['subfolder_mode']
        self.parent_mode = states['parent_mode']
        self.update_display_callback = update_display_callback

    def traverse_directory(self, new_path):
        """Set up for a new directory and create an updated slideshow."""
        if os.path.isdir(new_path):
            parent_image_dirs = {new_path: {"weight_modifier": 100, "is_percentage": True}}
            parent_tree = build_tree(self.defaults, self.filters, parent_image_dirs, None, self.quiet)
            new_image_paths, new_weights = extract_image_paths_and_weights_from_tree(parent_tree)
            self.update_slide_show(new_image_paths, new_weights)
        else:
            print("No valid directory found.")
            
    def navigate_up(self):
        """Navigate up one level in the directory structure."""
        if self.parentFolderStack.is_full() or not self.parent_mode:
            print("Cannot navigate up - Stack is full or not in parent mode.")
            return
        
        new_path = os.path.dirname(self.parentFolderStack.read_top())
        self.parentFolderStack.push(new_path, self.image_paths, self.weights)
        self.traverse_directory(new_path)

    def navigate_down(self):
        """Navigate down into the selected directory."""
        current_path = os.path.dirname(self.current_image_path)
        current_path_level = level_of(current_path)
    
        if current_path_level:
            new_path = truncate_path(current_path, current_path_level - 1)
            self.parentFolderStack.push(new_path, self.image_paths, self.weights)
            self.traverse_directory(new_path)
        else:
            print("No lower directory available.")

    def follow_branch_down(self, parent_mode, pFStackData, event=None):
        if self.subfolder_mode and parent_mode:
            self.subfolder_mode = False
        elif self.subfolder_mode:
            self.navigate_down()
        elif pFStackData:
            self.navigate_up()

    def follow_branch_up(self, event=None):
        if self.subfolder_mode:
            self.subfolder_mode = False
            self.on_image_change(self.image_paths[self.current_image_index])
            return
        self.navigate_up()