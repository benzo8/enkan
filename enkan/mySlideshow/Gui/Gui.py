"""
GUI utility wrapper for enkan slideshow.
Provides customtkinter-aware helpers with fallback to standard tkinter.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

# Try customtkinter + CTkMessagebox
try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
except ImportError:
    CTK_AVAILABLE = False

try:
    from CTkMessagebox import CTkMessagebox
    CTK_MESSAGEBOX_AVAILABLE = True
except ImportError:
    CTK_MESSAGEBOX_AVAILABLE = False

# Standard tkinter (always available)
import tkinter as tk
from tkinter import messagebox

# Local dialog classes
from .ModeAdjustDialog import ModeAdjustDialog

logger = logging.getLogger(__name__)


class Gui:
    """
    Encapsulates GUI toolkit selection and provides unified interface for dialogs.
    
    Usage:
        gui = Gui(use_customtkinter=True)  # auto-fallback if not installed
        gui.messagebox("Error", "Something went wrong", icon="warning")
    """

    def __init__(self, use_customtkinter: bool = True) -> None:
        """
        Initialize GUI helper.
        
        Args:
            use_customtkinter: Attempt to use customtkinter + CTkMessagebox if available.
        """
        self.ctk_enabled = use_customtkinter and CTK_AVAILABLE and CTK_MESSAGEBOX_AVAILABLE
        if use_customtkinter:
            if not CTK_AVAILABLE:
                logger.info("customtkinter requested but not installed; using standard tkinter")
            elif not CTK_MESSAGEBOX_AVAILABLE:
                logger.info("CTkMessagebox not installed; using standard tkinter messagebox")

    def messagebox(
        self,
        title: str,
        message: str,
        icon: Literal["info", "warning", "error"] = "info",
        type_: Literal["ok", "okcancel", "yesno"] = "ok",
    ) -> Optional[bool]:
        """
        Show a messagebox using CTkMessagebox (if enabled) or standard tkinter.

        Args:
            title: Dialog title.
            message: Message text.
            icon: Icon type (info, warning, error).
            type_: Button configuration (ok, okcancel, yesno).

        Returns:
            - None for "ok" type (no user choice).
            - True/False for okcancel/yesno (True = OK/Yes, False = Cancel/No).
        """
        if self.ctk_enabled:
            return self._ctk_messagebox(title, message, icon, type_)
        else:
            return self._tk_messagebox(title, message, icon, type_)

    def _ctk_messagebox(
        self, title: str, message: str, icon: str, type_: str
    ) -> Optional[bool]:
        """CTkMessagebox wrapper."""
        # CTkMessagebox icon names: "check", "cancel", "info", "question", "warning"
        icon_map = {"info": "info", "warning": "warning", "error": "cancel"}
        ctk_icon = icon_map.get(icon, "info")

        if type_ == "ok":
            CTkMessagebox(title=title, message=message, icon=ctk_icon)
            return None
        elif type_ == "okcancel":
            result = CTkMessagebox(
                title=title,
                message=message,
                icon=ctk_icon,
                option_1="Cancel",
                option_2="OK",
            )
            return result.get() == "OK"
        elif type_ == "yesno":
            result = CTkMessagebox(
                title=title,
                message=message,
                icon=ctk_icon,
                option_1="No",
                option_2="Yes",
            )
            return result.get() == "Yes"
        return None

    def _tk_messagebox(
        self, title: str, message: str, icon: str, type_: str
    ) -> Optional[bool]:
        """Standard tkinter messagebox wrapper."""
        if type_ == "ok":
            if icon == "info":
                messagebox.showinfo(title, message)
            elif icon == "warning":
                messagebox.showwarning(title, message)
            elif icon == "error":
                messagebox.showerror(title, message)
            return None
        elif type_ == "okcancel":
            if icon == "warning":
                return messagebox.askokcancel(title, message, icon="warning")
            else:
                return messagebox.askokcancel(title, message)
        elif type_ == "yesno":
            return messagebox.askyesno(title, message, icon=icon)
        return None

    def custom_dialog(
        self,
        parent,
        title: str,
        message: str,
        buttons: list[tuple[str, Optional[bool]]],
    ) -> Optional[bool]:
        """
        Show a custom dialog with configurable buttons.
        
        Args:
            parent: Parent tkinter window.
            title: Dialog title.
            message: Message text.
            buttons: List of (button_text, return_value) tuples.
        
        Returns:
            The value associated with the clicked button, or None if closed.
        """
        if self.ctk_enabled:
            return self._ctk_custom_dialog(parent, title, message, buttons)
        else:
            return self._tk_custom_dialog(parent, title, message, buttons)

    def _ctk_custom_dialog(
        self,
        parent,
        title: str,
        message: str,
        buttons: list[tuple[str, Optional[bool]]],
    ) -> Optional[bool]:
        """customtkinter custom dialog."""
        dialog = ctk.CTkToplevel(parent)
        dialog.title(title)
        dialog.transient(parent)
        dialog.grab_set()
        dialog.resizable(False, False)

        label = ctk.CTkLabel(dialog, text=message, justify="left", wraplength=400)
        label.pack(padx=24, pady=(24, 12))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=(0, 20))

        result: dict[str, Optional[bool]] = {"value": None}

        def close(value: Optional[bool] = None) -> None:
            result["value"] = value
            dialog.destroy()

        for text, value in buttons:
            ctk.CTkButton(
                btn_frame,
                text=text,
                command=lambda val=value: close(val),
            ).pack(side="left", padx=6)

        dialog.protocol("WM_DELETE_WINDOW", close)
        self._center_window(dialog)
        dialog.wait_window()
        return result["value"]

    def _tk_custom_dialog(
        self,
        parent,
        title: str,
        message: str,
        buttons: list[tuple[str, Optional[bool]]],
    ) -> Optional[bool]:
        """Standard tkinter custom dialog."""
        dialog = tk.Toplevel(parent)
        dialog.title(title)
        dialog.transient(parent)
        dialog.grab_set()
        dialog.resizable(False, False)

        label = tk.Label(dialog, text=message, justify="left", wraplength=400)
        label.pack(padx=24, pady=(24, 12))

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=(0, 20))

        result: dict[str, Optional[bool]] = {"value": None}

        def close(value: Optional[bool] = None) -> None:
            result["value"] = value
            dialog.destroy()

        for text, value in buttons:
            tk.Button(
                btn_frame,
                text=text,
                command=lambda val=value: close(val),
            ).pack(side="left", padx=6)

        dialog.protocol("WM_DELETE_WINDOW", close)
        self._center_window(dialog)
        dialog.wait_window()
        return result["value"]

    def _center_window(self, window: tk.Misc) -> None:
        """Center a Tk/CTk toplevel on the screen."""
        try:
            window.update_idletasks()
            width = window.winfo_width()
            height = window.winfo_height()
            if width <= 1 or height <= 1:
                width = window.winfo_reqwidth()
                height = window.winfo_reqheight()
            screen_w = window.winfo_screenwidth()
            screen_h = window.winfo_screenheight()
            x = max((screen_w - width) // 2, 0)
            y = max((screen_h - height) // 2, 0)
            window.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            pass

    # ---- Dialog factories ----
    def create_mode_adjust_dialog(
        self,
        parent: tk.Misc,
        current_mode: Optional[str],
        on_apply,
        on_reset,
        ignore_default: bool = False,
    ) -> ModeAdjustDialog:
        """Create and return a ModeAdjustDialog wired for the active toolkit.

        This keeps construction behind Gui so callers only import Gui.
        """
        return ModeAdjustDialog(
            parent=parent,
            initial_mode=current_mode,
            on_apply=on_apply,
            on_reset=on_reset,
            ignore_default=ignore_default,
        )