from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Callable, Optional, Any

from enkan.constants import CX_PATTERN

try:
    import customtkinter as ctk

    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
except ModuleNotFoundError:  # pragma: no cover - fallback for environments without CustomTkinter
    ctk = None


class ModeAdjustDialog:
    """Simple modal dialog used to tweak slideshow mode settings on the fly."""

    def __init__(
        self,
        parent: tk.Misc,
        initial_mode: Optional[str],
        on_apply: Callable[[str, bool], Optional[str]],
        on_reset: Callable[[], Optional[str]],
        ignore_default: bool = False,
        gui: Optional[Any] = None,
    ) -> None:
        self.parent = parent
        self.on_apply = on_apply
        self.on_reset = on_reset
        self.gui = gui

        self.top, ui, self._using_custom = self._initialise_ui(parent)

        self.top.title("Update Mode")
        self.top.transient(parent)
        self.top.grab_set()
        self.top.resizable(False, False)

        self.mode_var = self._make_stringvar((initial_mode or "").strip())
        self.ignore_var = self._make_boolvar(ignore_default)

        ui["label"](self.top, text="Mode string:").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 2))
        # Make the entry reasonably wide (pixels for CTk, characters for Tk)
        self.entry = ui["entry"](self.top, width=520 if ctk else 60, textvariable=self.mode_var)
        self.entry.grid(row=1, column=0, columnspan=3, padx=10, pady=(0, 10))
        self.entry.focus_set()

        self.ignore_checkbox = ui["check"](
            self.top,
            text="Ignore stored proportions",
            variable=self.ignore_var,
            onvalue=True if ctk else 1,
            offvalue=False if ctk else 0,
        )
        self.ignore_checkbox.grid(row=2, column=0, columnspan=3, padx=10, sticky="w")

        btn_frame = ui["frame"](self.top)
        btn_frame.grid(row=3, column=0, columnspan=3, pady=10)

        self.apply_btn = ui["button"](btn_frame, text="Apply", command=self._on_apply)
        self.apply_btn.pack(side="left", padx=5)

        self.reset_btn = ui["button"](btn_frame, text="Reset to Original", command=self._on_reset)
        self.reset_btn.pack(side="left", padx=5)

        self.cancel_btn = ui["button"](btn_frame, text="Cancel", command=self.close)
        self.cancel_btn.pack(side="left", padx=5)

        # Enforce a sensible minimum dialog size before centering
        try:
            self.top.update_idletasks()
            self.top.minsize(560, 180)
        except Exception:
            pass

        self.entry.bind("<Return>", lambda *_: self._on_apply())
        self.top.protocol("WM_DELETE_WINDOW", self.close)

        # Center on screen after widgets are laid out
        self._center_on_screen()

    def _initialise_ui(self, parent: tk.Misc) -> tuple[tk.Toplevel, dict[str, Callable[..., Any]], bool]:
        if ctk:
            top = ctk.CTkToplevel(parent)
            return top, {
                "label": ctk.CTkLabel,
                "entry": ctk.CTkEntry,
                "check": ctk.CTkCheckBox,
                "frame": ctk.CTkFrame,
                "button": ctk.CTkButton,
            }, True
        top = tk.Toplevel(parent)
        return top, {
            "label": tk.Label,
            "entry": tk.Entry,
            "check": tk.Checkbutton,
            "frame": tk.Frame,
            "button": tk.Button,
        }, False

    def _make_stringvar(self, value: str) -> tk.StringVar:
        if self._using_custom and ctk:
            return ctk.StringVar(master=self.top, value=value)
        return tk.StringVar(value=value)

    def _make_boolvar(self, value: bool) -> tk.BooleanVar:
        if self._using_custom and ctk:
            return ctk.BooleanVar(master=self.top, value=value)
        bool_var = tk.BooleanVar(value=value)
        bool_var.set(value)
        return bool_var

    def _validate_entry(self, value: str) -> bool:
        if not value:
            return False
        return bool(CX_PATTERN.fullmatch(value.strip()))

    def _center_on_screen(self) -> None:
        """Center the dialog on the primary screen."""
        try:
            self.top.update_idletasks()
            width = self.top.winfo_width()
            height = self.top.winfo_height()
            # When not yet drawn, winfo_width/height can be very small; fallback to requested size
            if width <= 1 or height <= 1:
                width = self.top.winfo_reqwidth()
                height = self.top.winfo_reqheight()
            screen_w = self.top.winfo_screenwidth()
            screen_h = self.top.winfo_screenheight()
            x = max((screen_w - width) // 2, 0)
            y = max((screen_h - height) // 2, 0)
            self.top.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            # Positioning isn't critical; ignore failures gracefully
            pass

    def _on_apply(self) -> None:
        value = self.mode_var.get().strip()
        if not self._validate_entry(value):
            self._show_error("Invalid Mode", "Mode string must match CX pattern.")
            return
        try:
            new_value = self.on_apply(value, bool(self.ignore_var.get()))
        except ValueError as exc:  # pragma: no cover - UI feedback path
            self._show_error("Update Failed", str(exc))
            return
        if new_value is not None:
            self.mode_var.set(new_value.strip())
        self.close()

    def _on_reset(self) -> None:
        try:
            value = self.on_reset()
        except ValueError as exc:  # pragma: no cover - UI feedback path
            self._show_error("Reset Failed", str(exc))
            return
        if value:
            self.mode_var.set(value.strip())
            self.ignore_var.set(False)

    def _show_error(self, title: str, message: str) -> None:
        """Show an error using Gui.messagebox when available, else fallback to tkinter.messagebox."""
        try:
            if self.gui and hasattr(self.gui, "messagebox"):
                self.gui.messagebox(title=title, message=message, icon="error", type_="ok", parent=self.top)
            else:
                messagebox.showerror(title, message, parent=self.top)
        except Exception:
            # Last resort fallback without parent if something odd happens
            try:
                messagebox.showerror(title, message)
            except Exception:
                pass

    def close(self) -> None:
        self.top.grab_release()
        self.top.destroy()
