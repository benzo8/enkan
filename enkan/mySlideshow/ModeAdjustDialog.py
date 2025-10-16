from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Callable, Optional

from enkan.constants import CX_PATTERN


class ModeAdjustDialog:
    """Simple modal dialog used to tweak slideshow mode settings on the fly."""

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        initial_mode: Optional[str],
        on_apply: Callable[[str, bool], Optional[str]],
        on_reset: Callable[[], Optional[str]],
        ignore_default: bool = False,
    ) -> None:
        self.parent = parent
        self.on_apply = on_apply
        self.on_reset = on_reset

        self.top = tk.Toplevel(parent)
        self.top.title("Update Mode")
        self.top.transient(parent)
        self.top.grab_set()
        self.top.resizable(False, False)

        self.mode_var = tk.StringVar(value=(initial_mode or "").strip())
        self.ignore_var = tk.BooleanVar(value=ignore_default)

        tk.Label(self.top, text="Mode string:").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 2))
        self.entry = tk.Entry(self.top, width=40, textvariable=self.mode_var)
        self.entry.grid(row=1, column=0, columnspan=3, padx=10, pady=(0, 10))
        self.entry.focus_set()

        self.ignore_checkbox = tk.Checkbutton(
            self.top,
            text="Ignore stored proportions",
            variable=self.ignore_var,
        )
        self.ignore_checkbox.grid(row=2, column=0, columnspan=3, padx=10, sticky="w")

        btn_frame = tk.Frame(self.top)
        btn_frame.grid(row=3, column=0, columnspan=3, pady=10)

        self.apply_btn = tk.Button(btn_frame, text="Apply", command=self._on_apply)
        self.apply_btn.pack(side=tk.LEFT, padx=5)

        self.reset_btn = tk.Button(btn_frame, text="Reset to Original", command=self._on_reset)
        self.reset_btn.pack(side=tk.LEFT, padx=5)

        self.cancel_btn = tk.Button(btn_frame, text="Cancel", command=self.close)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)

        self.entry.bind("<Return>", lambda *_: self._on_apply())
        self.top.protocol("WM_DELETE_WINDOW", self.close)

    def _validate_entry(self, value: str) -> bool:
        if not value:
            return False
        return bool(CX_PATTERN.fullmatch(value.strip()))

    def _on_apply(self) -> None:
        value = self.mode_var.get().strip()
        if not self._validate_entry(value):
            messagebox.showerror("Invalid Mode", "Mode string must match CX pattern.", parent=self.top)
            return
        try:
            new_value = self.on_apply(value, self.ignore_var.get())
        except ValueError as exc:
            messagebox.showerror("Update Failed", str(exc), parent=self.top)
            return
        if new_value is not None:
            self.mode_var.set(new_value.strip())
        self.close()

    def _on_reset(self) -> None:
        try:
            value = self.on_reset()
        except ValueError as exc:
            messagebox.showerror("Reset Failed", str(exc), parent=self.top)
            return
        if value:
            self.mode_var.set(value.strip())
            self.ignore_var.set(False)

    def close(self) -> None:
        self.top.grab_release()
        self.top.destroy()
