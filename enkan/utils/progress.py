"""
Progress bar wrapper that keeps console tqdm output unchanged while optionally
showing a transient Tkinter toast bar. Both bars can be silenced via a shared
quiet flag so callers can treat this as a drop-in replacement for `tqdm(...)`.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Iterable, Iterator, Optional, Protocol

from enkan.utils.Defaults import get_current_defaults

from tqdm import tqdm

logger = logging.getLogger(__name__)


class _TkProgressProtocol(Protocol):
    def update(
        self, n: int = 1, total: Optional[int] = None, desc: Optional[str] = None
    ) -> None: ...

    def close(self) -> None: ...


class _NullProgress:
    """
    No-op progress stand-in used when quiet is requested. It maintains the
    surface area expected from tqdm so existing callers keep working.
    """

    def __init__(
        self,
        iterable: Optional[Iterable[Any]] = None,
        total: Optional[int] = None,
        desc: str | None = None,
    ) -> None:
        self.iterable = iterable
        self.total = total
        self.desc = desc or ""
        self.leave = True

    def __iter__(self) -> Iterator[Any]:
        if self.iterable is None:
            return iter(())
        for item in self.iterable:
            yield item

    def __enter__(self) -> "_NullProgress":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    def update(self, n: int = 1) -> None:
        return None

    def refresh(self) -> None:
        return None

    def close(self) -> None:
        return None

    def set_description(self, desc: str, refresh: bool = True) -> None:
        self.desc = desc


class TkProgressToast:
    """
    Lightweight Tkinter toast with a progress bar anchored near the bottom of
    the screen. Runs synchronously so it paints even while the main loop is busy.
    """

    def __init__(
        self,
        root: Any,
        total: Optional[int],
        desc: Optional[str],
        *,
        width: int = 320,
        padding: int = 12,
    ) -> None:
        self.root = root
        self.total = total or 0
        self.value = 0
        self._closed = False

        try:
            import tkinter as tk
            from tkinter import ttk
        except Exception as exc:  # pragma: no cover - Tk import failures
            logger.debug("Tkinter not available for progress toast: %s", exc)
            self._closed = True
            return

        self.window = tk.Toplevel(root)
        self.window.wm_overrideredirect(True)
        self.window.withdraw()  # position before showing to avoid top-left flash
        self.window.configure(bg="#111")

        wrap = max(120, width - (padding * 2))
        self._wraplength = wrap
        trimmed_desc = self._trim_desc(desc or "")
        self.label = tk.Label(
            self.window,
            text=trimmed_desc,
            fg="#eee",
            bg="#111",
            anchor="center",
            justify="center",
            padx=padding,
            pady=padding,
            wraplength=wrap,
        )
        self.label.pack(fill="x")

        self.progress = ttk.Progressbar(self.window, mode="determinate")
        self._configure_progress_max(self.total)
        self.progress.pack(fill="x", padx=padding, pady=(0, padding))

        self._place_and_show(width)
        logger.debug(
            "Tk progress toast created with total=%s desc=%s", self.total, desc
        )

    def _place_and_show(self, width: int) -> None:
        try:
            self.window.update_idletasks()
        except Exception:
            return
        try:
            master = self.window.master
            master.update_idletasks()
            root_w = master.winfo_width()
            root_h = master.winfo_height()
            root_x = master.winfo_rootx()
            root_y = master.winfo_rooty()
        except Exception:
            root_w = self.window.winfo_screenwidth()
            root_h = self.window.winfo_screenheight()
            root_x = 0
            root_y = 0

        if root_w < 50 or root_h < 50:
            root_w = self.window.winfo_screenwidth()
            root_h = self.window.winfo_screenheight()
            root_x = 0
            root_y = 0

        try:
            content_height = self.window.winfo_reqheight()
        except Exception:
            content_height = 64
        height = max(64, min(content_height, max(root_h - 20, 64)))
        x = int(root_x + (root_w - width) / 2)
        y = int(root_y + root_h - height - 40)
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        try:
            self.window.deiconify()
            self._ensure_visible()
        except Exception:
            pass

    def _configure_progress_max(self, total: Optional[int]) -> None:
        try:
            if total and total > 0:
                self.progress.configure(mode="determinate", maximum=max(total, 1))
                try:
                    self.progress.stop()
                except Exception:
                    pass
            else:
                self.progress.configure(mode="indeterminate")
                try:
                    self.progress.start(50)
                except Exception:
                    pass
        except Exception:
            pass

    def _ensure_visible(self) -> None:
        try:
            self.window.attributes("-topmost", True)
            self.window.lift()
            self.window.update_idletasks()
        except Exception:
            pass

    def _dispatch(self, fn: Callable[[], None]) -> None:
        if self._closed or not hasattr(self, "window"):
            return
        try:
            fn()
            try:
                self.window.update_idletasks()
                self.window.update()
            except Exception:
                pass
        except Exception:
            try:
                self.window.after(0, fn)
            except Exception:
                self._closed = True

    def update(
        self, n: int = 1, total: Optional[int] = None, desc: Optional[str] = None
    ) -> None:
        if self._closed or not hasattr(self, "window"):
            return

        def _apply() -> None:
            if self._closed:
                return
            self._ensure_visible()
            if total is not None:
                self.total = total
                self._configure_progress_max(total)
            if self.total and self.total > 0:
                self.value = min(self.value + n, self.total)
                self.progress["value"] = self.value
            else:
                try:
                    self.progress.step()
                except Exception:
                    pass
            if desc is not None:
                self.label.config(text=self._trim_desc(desc))
            if self.total and self.value >= self.total:
                self.window.after(300, self.close)

        self._dispatch(_apply)

    def close(self) -> None:
        if self._closed or not hasattr(self, "window"):
            return

        def _destroy() -> None:
            if self._closed:
                return
            try:
                self.window.destroy()
            except Exception:
                pass
            self._closed = True

        self._dispatch(_destroy)

    def _trim_desc(self, desc: str) -> str:
        """
        Trim to roughly two lines by clipping the middle while preserving start/end.
        """
        if not desc:
            return ""
        avg_char_px = 7
        max_chars_per_line = max(20, int(self._wraplength / avg_char_px))
        max_chars = max_chars_per_line * 2
        if len(desc) <= max_chars:
            return desc
        keep = max_chars - 5
        front = keep // 2
        back = keep - front
        return f"{desc[:front]} ... {desc[-back:]}"


class Progress:
    """
    Combined progress controller that mirrors tqdm's interface while optionally
    driving a Tk toast. Intended drop-in: replace `tqdm(...)` with `progress(...)`.
    """

    def __init__(
        self,
        iterable: Optional[Iterable[Any]] = None,
        *,
        tk_root: Any = None,
        tk_enabled: bool = True,
        **tqdm_kwargs: Any,
    ) -> None:
        self.defaults = get_current_defaults()
        quiet = self.defaults.quiet
        self._iterable = iterable
        self._tqdm_kwargs = tqdm_kwargs
        self._console = (
            _NullProgress(iterable, tqdm_kwargs.get("total"), tqdm_kwargs.get("desc"))
            if quiet
            else tqdm(iterable, **tqdm_kwargs)
        )
        self._tk: Optional[_TkProgressProtocol] = None
        self._lock = threading.Lock()

        root_candidate = tk_root
        if root_candidate is None and tk_enabled and not quiet:
            try:
                import tkinter as tk  # type: ignore[import]

                root_candidate = getattr(tk, "_default_root", None)
            except Exception:
                root_candidate = None

        if not quiet and tk_enabled and root_candidate is not None:
            try:
                self._tk = TkProgressToast(
                    root_candidate, tqdm_kwargs.get("total"), tqdm_kwargs.get("desc")
                )
            except (
                Exception
            ) as exc:  # pragma: no cover - Tk issues shouldn't break console
                logger.debug("Failed to initialise Tk progress toast: %s", exc)

    @property
    def total(self) -> Optional[int]:
        return getattr(self._console, "total", None)

    @total.setter
    def total(self, value: Optional[int]) -> None:
        if hasattr(self._console, "total"):
            self._console.total = value
        if self._tk:
            self._tk.update(0, total=value)

    @property
    def desc(self) -> str:
        return getattr(self._console, "desc", "")

    @desc.setter
    def desc(self, value: str) -> None:
        if hasattr(self._console, "desc"):
            self._console.desc = value
        if self._tk:
            self._tk.update(0, desc=value)

    @property
    def leave(self) -> bool:
        return getattr(self._console, "leave", True)

    @leave.setter
    def leave(self, value: bool) -> None:
        if hasattr(self._console, "leave"):
            self._console.leave = value

    def __iter__(self) -> Iterator[Any]:
        if self._iterable is None:
            return iter(())
        for item in self._iterable:
            yield item
            self.update(1)

    def __enter__(self) -> "Progress":
        if hasattr(self._console, "__enter__"):
            self._console.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            if hasattr(self._console, "__exit__"):
                self._console.__exit__(exc_type, exc_val, exc_tb)
        finally:
            self.close()
        return None

    def update(self, n: int = 1) -> None:
        with self._lock:
            try:
                self._console.update(n)
            finally:
                if self._tk:
                    self._tk.update(n, total=self.total, desc=self.desc)

    def set_description(self, desc: str, refresh: bool = True) -> None:
        self.desc = desc
        if refresh:
            self.refresh()

    def refresh(self) -> None:
        if hasattr(self._console, "refresh"):
            self._console.refresh()

    def close(self) -> None:
        if self._tk:
            self._tk.close()
            self._tk = None
        if hasattr(self._console, "close"):
            self._console.close()


def progress(
    iterable: Optional[Iterable[Any]] = None,
    *,
    tk_root: Any = None,
    tk_enabled: bool = True,
    **tqdm_kwargs: Any,
) -> Progress:
    """
    Factory matching `tqdm(iterable, **kwargs)` but with optional Tk toast and
    quiet support. Callers can use this as a drop-in replacement.
    """

    return Progress(iterable, tk_root=tk_root, tk_enabled=tk_enabled, **tqdm_kwargs)
