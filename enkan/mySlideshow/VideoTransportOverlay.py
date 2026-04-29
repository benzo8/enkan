import tkinter as tk
from typing import Callable

from enkan.mySlideshow.VideoPlaybackController import VideoPlaybackSnapshot


class VideoTransportOverlay:
    """Bottom-reveal transport controls for active video playback."""

    REVEAL_EDGE_PX = 80
    HIDE_AFTER_MS = 2000
    REFRESH_MS = 500

    def __init__(
        self,
        root: tk.Misc,
        snapshot_provider: Callable[[], VideoPlaybackSnapshot],
        toggle_pause: Callable[[], bool],
        seek_to_ratio: Callable[[float], bool],
    ) -> None:
        self.root = root
        self.snapshot_provider = snapshot_provider
        self.toggle_pause = toggle_pause
        self.seek_to_ratio = seek_to_ratio

        self._active = False
        self._visible = False
        self._hide_after_id = None
        self._refresh_after_id = None
        self._updating_scale = False

        self.frame = tk.Frame(root, bg="#111111")
        self.pause_button = tk.Button(
            self.frame,
            text="Pause",
            command=self._on_pause,
            width=8,
        )
        self.time_label = tk.Label(
            self.frame,
            text="--:-- / --:--",
            bg="#111111",
            fg="white",
            width=15,
        )
        self.progress = tk.Scale(
            self.frame,
            from_=0,
            to=1000,
            orient=tk.HORIZONTAL,
            showvalue=False,
            command=self._on_seek,
            length=320,
        )
        self.pause_button.pack(side=tk.LEFT, padx=(8, 4), pady=6)
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.time_label.pack(side=tk.LEFT, padx=(4, 8))

    def set_active(self, active: bool) -> None:
        self._active = active
        if not active:
            self.hide()

    def handle_motion(self, event) -> None:
        if not self._active:
            return
        window_height = self.root.winfo_height()
        if getattr(event, "y", 0) >= window_height - self.REVEAL_EDGE_PX:
            self.show()

    def show(self) -> None:
        if not self._active:
            return
        self._visible = True
        height = 48
        self.frame.place(
            x=0,
            y=max(0, self.root.winfo_height() - height),
            width=self.root.winfo_width(),
            height=height,
        )
        self.frame.lift()
        self.refresh()
        self._schedule_hide()

    def hide(self) -> None:
        self._visible = False
        self.frame.place_forget()
        self._cancel_after("_hide_after_id")
        self._cancel_after("_refresh_after_id")

    def refresh(self) -> None:
        if not self._active or not self._visible:
            return
        snapshot = self.snapshot_provider()
        if not snapshot.active:
            self.hide()
            return

        self.pause_button.config(text="Play" if snapshot.paused else "Pause")
        self.time_label.config(
            text=f"{self._format_time(snapshot.current_time_ms)} / "
            f"{self._format_time(snapshot.duration_ms)}"
        )
        ratio = snapshot.progress_ratio
        self._updating_scale = True
        self.progress.set(0 if ratio is None else int(ratio * 1000))
        self.progress.config(state=tk.NORMAL if snapshot.seekable else tk.DISABLED)
        self._updating_scale = False
        self._schedule_refresh()

    def _on_pause(self) -> None:
        self.toggle_pause()
        self.refresh()
        self._schedule_hide()

    def _on_seek(self, value: str) -> None:
        if self._updating_scale:
            return
        try:
            ratio = float(value) / 1000
        except ValueError:
            return
        self.seek_to_ratio(ratio)
        self.refresh()
        self._schedule_hide()

    def _schedule_hide(self) -> None:
        self._cancel_after("_hide_after_id")
        self._hide_after_id = self.root.after(self.HIDE_AFTER_MS, self.hide)

    def _schedule_refresh(self) -> None:
        self._cancel_after("_refresh_after_id")
        self._refresh_after_id = self.root.after(self.REFRESH_MS, self.refresh)

    def _cancel_after(self, attr_name: str) -> None:
        after_id = getattr(self, attr_name)
        if after_id is None:
            return
        try:
            self.root.after_cancel(after_id)
        except tk.TclError:
            pass
        setattr(self, attr_name, None)

    @staticmethod
    def _format_time(value_ms: int | None) -> str:
        if value_ms is None or value_ms < 0:
            return "--:--"
        total_seconds = value_ms // 1000
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:d}:{seconds:02d}"
