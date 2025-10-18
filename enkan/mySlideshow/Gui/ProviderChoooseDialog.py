import tkinter as tk
from tkinter import simpledialog, messagebox

class ProviderChooserDialog(simpledialog.Dialog):
    def __init__(self, parent, provider_names, title="Choose Image Provider"):
        self.provider_names = provider_names
        self.selected_provider = provider_names[0]
        self.extra_kwargs = {}
        super().__init__(parent, title)

    def body(self, master):
        tk.Label(master, text="Select image provider:").pack(padx=10, pady=10)
        self.var = tk.StringVar(value=self.provider_names[0])
        self.dropdown = tk.OptionMenu(master, self.var, *self.provider_names, command=self.on_provider_change)
        self.dropdown.pack(padx=10, pady=(0, 10))
        # Placeholder for extra arg widgets
        self.extra_frame = tk.Frame(master)
        self.extra_frame.pack()
        self.weight_entry = None
        self.on_provider_change(self.provider_names[0])
        return self.dropdown

    def on_provider_change(self, selected):
        # Remove any extra fields
        for widget in self.extra_frame.winfo_children():
            widget.destroy()
        self.extra_kwargs.clear()

        if selected == "weighted":
            tk.Label(self.extra_frame, text="Weights (comma-separated):").pack(side=tk.LEFT)
            self.weight_entry = tk.Entry(self.extra_frame)
            self.weight_entry.pack(side=tk.LEFT)

    def apply(self):
        self.selected_provider = self.var.get()
        if self.selected_provider == "weighted" and self.weight_entry:
            weights_text = self.weight_entry.get()
            try:
                weights = [float(w.strip()) for w in weights_text.split(',') if w.strip()]
                self.extra_kwargs['weights'] = weights
            except Exception:
                messagebox.showerror("Invalid Weights", "Weights must be a comma-separated list of numbers.")
                self.extra_kwargs['weights'] = []
        # Add more provider-specific arguments as needed

def choose_and_set_provider(root, providers_instance, image_paths):
    provider_names = list(providers_instance.providers.keys())
    dlg = ProviderChooserDialog(root, provider_names)
    chosen = dlg.selected_provider
    kwargs = dlg.extra_kwargs
    if chosen:
        providers_instance.reset_manager(image_paths, provider_name=chosen, **kwargs)
        tk.messagebox.showinfo("Provider Changed", f"Provider switched to: {chosen}")

# Usage remains:
# root.bind('<p>', lambda event: choose_and_set_provider(root, providers, image_paths))