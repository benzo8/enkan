from dataclasses import dataclass
from enum import Enum
import threading
import tkinter as tk
import tkinter.font as tkfont
from typing import Protocol


VIDEO_TIMER_STATUS_KEY = "video-timer"
VIDEO_RUNTIME_STATUS_KEY = "video-runtime-status"
FILEPATH_STATUS_KEY = "filepath"
IMAGE_META_STATUS_KEY = "image-meta"
RUNTIME_STATUS_KEY = "runtime-status"
AUTO_ADVANCE_STATUS_KEY = "auto-advance"
COUNT_STATUS_KEY = "count"
SCOPE_STATUS_KEY = "scope"
CACHE_DOTS_STATUS_KEY = "cache-dots"
PROVIDER_LABEL_STATUS_KEY = "provider-label"
PROVIDER_DETAIL_STATUS_KEY = "provider-detail"
PROVIDER_BURST_DOTS_STATUS_KEY = "provider-burst-dots"


@dataclass(frozen=True)
class StatusSegment:
    text: str
    tag: str


@dataclass(frozen=True)
class FilenameDisplay:
    segments: tuple[StatusSegment, ...]
    fixed_colour: str
    width: int


@dataclass(frozen=True)
class StatusDisplay:
    filename: FilenameDisplay
    center: "StatusZoneRender"
    right: "StatusZoneRender"

    @property
    def center_text(self) -> str:
        return self.center.text

    @property
    def mode_text(self) -> str:
        return self.right.text


class StatusSink(Protocol):
    def set_contribution(self, contribution: "StatusContribution") -> None: ...

    def set_contributions(
        self,
        contributions: list["StatusContribution"] | tuple["StatusContribution", ...],
    ) -> None: ...

    def clear_contribution(self, key: str) -> None: ...


class StatusBar:
    def __init__(self, root) -> None:
        self.root = root
        self._ui_thread_id = threading.get_ident()
        self._visible = False
        self._base_contributions: dict[str, StatusContribution] = {}
        self._owned_contributions: dict[str, StatusContribution] = {}
        self._hidden_contribution_keys: set[str] = set()
        self.status_band = tk.Frame(
            root,
            bg="black",
            bd=0,
            highlightthickness=0,
        )
        self.filename_label = tk.Text(
            root,
            bg="black",
            fg="white",
            height=1,
            wrap="none",
            bd=0,
            highlightthickness=0,
        )
        self.filename_label.config(state=tk.DISABLED)
        self.center_label = tk.Text(
            root,
            bg="black",
            fg="white",
            height=1,
            wrap="none",
            bd=0,
            highlightthickness=0,
        )
        self.center_label.config(state=tk.DISABLED)
        self.mode_label = tk.Text(
            root,
            bg="black",
            fg="white",
            height=1,
            wrap="none",
            bd=0,
            highlightthickness=0,
        )
        self.mode_label.config(state=tk.DISABLED)

    def raise_widgets(self) -> None:
        self.status_band.tkraise()
        self.filename_label.tkraise()
        self.center_label.tkraise()
        self.mode_label.tkraise()

    def hide(self) -> None:
        self.status_band.place_forget()
        self.filename_label.place_forget()
        self.center_label.place_forget()
        self.mode_label.place_forget()

    def set_base_contributions(
        self,
        contributions: list["StatusContribution"] | tuple["StatusContribution", ...],
        *,
        visible: bool,
    ) -> None:
        self._base_contributions = {
            contribution.key: contribution for contribution in contributions
        }
        self._visible = visible
        self._refresh_visible_status()

    def set_contribution(self, contribution: "StatusContribution") -> None:
        if self._should_marshal_to_ui_thread():
            self._schedule_on_ui_thread(lambda: self.set_contribution(contribution))
            return
        self._owned_contributions[contribution.key] = contribution
        self._refresh_visible_status()

    def set_contributions(
        self,
        contributions: list["StatusContribution"] | tuple["StatusContribution", ...],
    ) -> None:
        if self._should_marshal_to_ui_thread():
            self._schedule_on_ui_thread(lambda: self.set_contributions(contributions))
            return
        for contribution in contributions:
            self._owned_contributions[contribution.key] = contribution
        self._refresh_visible_status()

    def clear_contribution(self, key: str) -> None:
        if self._should_marshal_to_ui_thread():
            self._schedule_on_ui_thread(lambda: self.clear_contribution(key))
            return
        if key in self._owned_contributions:
            del self._owned_contributions[key]
            self._refresh_visible_status()

    def set_contribution_visible(self, key: str, visible: bool) -> None:
        if visible:
            self._hidden_contribution_keys.discard(key)
        else:
            self._hidden_contribution_keys.add(key)
        self._refresh_visible_status()

    def toggle_contribution_visibility(self, key: str) -> bool:
        visible = key in self._hidden_contribution_keys
        self.set_contribution_visible(key, visible)
        return visible

    def _should_marshal_to_ui_thread(self) -> bool:
        ui_thread_id = getattr(self, "_ui_thread_id", threading.get_ident())
        return threading.get_ident() != ui_thread_id

    def _schedule_on_ui_thread(self, callback) -> None:
        after = getattr(self.root, "after", None)
        if callable(after):
            after(0, callback)

    def _merged_contributions(self) -> tuple["StatusContribution", ...]:
        hidden_keys = getattr(self, "_hidden_contribution_keys", set())
        merged = {
            **self._base_contributions,
            **self._owned_contributions,
        }
        return tuple(
            contribution
            for contribution in merged.values()
            if contribution.key not in hidden_keys
        )

    def _refresh_visible_status(self) -> None:
        if not self._visible:
            self.hide()
            self.root.update_idletasks()
            return
        self.update(build_status_display(self._merged_contributions()), visible=True)

    def update(self, display: StatusDisplay | None, *, visible: bool) -> None:
        self._visible = visible
        if not visible or display is None:
            self.hide()
            self.root.update_idletasks()
            return

        status_height = self._status_height()
        self.status_band.place(
            x=0,
            y=0,
            width=self.root.winfo_screenwidth(),
            height=status_height,
        )

        filename_display = display.filename
        self.filename_label.config(state=tk.NORMAL)
        self.filename_label.delete("1.0", tk.END)
        for segment in filename_display.segments:
            self.filename_label.insert(tk.END, segment.text, segment.tag)

        self.filename_label.tag_configure(
            "fixed", foreground=filename_display.fixed_colour
        )
        self.filename_label.tag_configure("normal", foreground="white")
        self.filename_label.tag_configure("meta", foreground="white")
        self.filename_label.tag_configure("timer", foreground="white")
        self.filename_label.tag_configure("separator", foreground="white")
        self.filename_label.tag_configure("dot-full", foreground="green")
        self.filename_label.tag_configure("dot-empty", foreground="grey")
        self.filename_label.tag_configure("dot-overflow", foreground="white")
        self.filename_label.place(x=0, y=0, height=status_height)
        self.filename_label.config(height=1, width=filename_display.width, bg="black")
        self.filename_label.config(state=tk.DISABLED)

        self.mode_label.config(state=tk.NORMAL)
        self.mode_label.delete("1.0", tk.END)
        for segment in display.right.segments:
            self.mode_label.insert(tk.END, segment.text, segment.tag)
        self.mode_label.tag_configure("normal", foreground="white")
        self.mode_label.tag_configure("separator", foreground="white")
        self.mode_label.tag_configure("dot-full", foreground="green")
        self.mode_label.tag_configure("dot-empty", foreground="grey")
        self.mode_label.tag_configure("dot-overflow", foreground="white")
        self.mode_label.config(state=tk.DISABLED, bg="black")
        self.center_label.config(state=tk.NORMAL)
        self.center_label.delete("1.0", tk.END)
        for segment in display.center.segments:
            self.center_label.insert(tk.END, segment.text, segment.tag)
        self.center_label.tag_configure("normal", foreground="white")
        self.center_label.tag_configure("separator", foreground="white")
        self.center_label.tag_configure("dot-full", foreground="green")
        self.center_label.tag_configure("dot-empty", foreground="grey")
        self.center_label.tag_configure("dot-overflow", foreground="white")
        self.center_label.config(
            state=tk.DISABLED,
        )
        if display.center_text:
            text_width = tkfont.Font(font=self.center_label.cget("font")).measure(
                display.center_text
            )
            self.center_label.place(
                x=self.root.winfo_screenwidth() // 2,
                y=0,
                height=status_height,
                width=max(text_width + 8, 1),
                anchor="n",
            )
        else:
            self.center_label.place_forget()
        if display.mode_text:
            mode_width = tkfont.Font(font=self.mode_label.cget("font")).measure(
                display.mode_text
            )
            self.mode_label.place(
                x=self.root.winfo_screenwidth(),
                y=0,
                height=status_height,
                width=max(mode_width + 8, 1),
                anchor="ne",
            )
        else:
            self.mode_label.place_forget()
        self.raise_widgets()
        self.root.update_idletasks()

    def _status_height(self) -> int:
        fonts = (
            tkfont.Font(font=self.filename_label.cget("font")),
            tkfont.Font(font=self.center_label.cget("font")),
            tkfont.Font(font=self.mode_label.cget("font")),
        )
        return max(font.metrics("linespace") for font in fonts) + 4


class StatusZone(str, Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class StatusKind(str, Enum):
    TEXT = "text"
    FILEPATH = "filepath"
    TIMER = "timer"
    DOTS = "dots"
    GRAPH = "graph"


@dataclass(frozen=True)
class StatusFilePath:
    label_path: str
    fixed_path: str | None = None
    fixed_colour: str | None = None


@dataclass(frozen=True)
class StatusTimer:
    current_ms: int | None
    duration_ms: int | None = None
    paused: bool = False
    status_text: str = ""
    label: str = "VIDEO"
    prefix: str = ""
    suffix: str = ""


def build_video_timer_contribution(
    *,
    current_ms: int | None,
    duration_ms: int | None,
    paused: bool,
    status_text: str,
) -> "StatusContribution":
    return StatusContribution(
        VIDEO_TIMER_STATUS_KEY,
        StatusZone.LEFT,
        90,
        kind=StatusKind.TIMER,
        content=StatusTimer(
            current_ms=current_ms,
            duration_ms=duration_ms,
            paused=paused,
            status_text=status_text.upper() if status_text else "",
            prefix=" { ",
            suffix=" }",
        ),
    )


def build_video_runtime_status_contribution(status_text: str) -> "StatusContribution":
    return StatusContribution(
        VIDEO_RUNTIME_STATUS_KEY,
        StatusZone.RIGHT,
        30,
        content=f"VIDEO: {status_text}" if status_text else "",
    )


def build_filepath_contribution(
    label_path: str,
    fixed_path: str | None,
    fixed_colour: str | None,
) -> "StatusContribution":
    return StatusContribution(
        FILEPATH_STATUS_KEY,
        StatusZone.LEFT,
        100,
        kind=StatusKind.FILEPATH,
        content=StatusFilePath(label_path, fixed_path, fixed_colour),
    )


def build_image_meta_contribution(
    rotation_text: str,
    zoom_percent: int,
) -> "StatusContribution":
    return StatusContribution(
        IMAGE_META_STATUS_KEY,
        StatusZone.LEFT,
        90,
        content=f" ({rotation_text}, {zoom_percent}%)",
        style="meta",
    )


def build_runtime_status_contribution(status_text: str) -> "StatusContribution":
    return StatusContribution(
        RUNTIME_STATUS_KEY,
        StatusZone.RIGHT,
        30,
        content=status_text,
    )


def build_auto_advance_contribution(
    running: bool,
    interval: int | float | None,
) -> "StatusContribution | None":
    if not running or interval is None or interval <= 0:
        return None
    return StatusContribution(
        AUTO_ADVANCE_STATUS_KEY,
        StatusZone.RIGHT,
        0,
        content=f"AUTO ({interval}ms)  ",
    )


def build_count_contribution(
    current_image_path: str | None,
    image_paths: list[str],
    current_image_index: int,
) -> "StatusContribution":
    return StatusContribution(
        COUNT_STATUS_KEY,
        StatusZone.RIGHT,
        10,
        content=_count_text(current_image_path, image_paths, current_image_index),
    )


def build_scope_contribution(
    subfolder_mode: bool,
    parent_mode: bool,
) -> "StatusContribution | None":
    scope_parts: list[str] = []
    if subfolder_mode:
        scope_parts.append("SUB")
    if parent_mode:
        scope_parts.append("PAR")
    if not scope_parts:
        return None
    return StatusContribution(
        SCOPE_STATUS_KEY,
        StatusZone.RIGHT,
        40,
        content=" ".join(scope_parts),
    )


def build_cache_dots_contribution(
    full: int,
    total: int,
) -> "StatusContribution":
    return StatusContribution(
        CACHE_DOTS_STATUS_KEY,
        StatusZone.CENTER,
        50,
        kind=StatusKind.DOTS,
        content=StatusDots(full=full, total=total),
    )


def build_provider_label_contribution(label: str, *, priority: int = 100) -> "StatusContribution":
    return StatusContribution(
        PROVIDER_LABEL_STATUS_KEY,
        StatusZone.RIGHT,
        priority,
        content=label or "-",
    )


def build_provider_detail_contribution(detail: str) -> "StatusContribution":
    return StatusContribution(
        PROVIDER_DETAIL_STATUS_KEY,
        StatusZone.RIGHT,
        90,
        content=detail,
    )


def build_provider_burst_dots_contribution(
    full: int,
    total: int,
) -> "StatusContribution":
    return StatusContribution(
        PROVIDER_BURST_DOTS_STATUS_KEY,
        StatusZone.RIGHT,
        95,
        kind=StatusKind.DOTS,
        content=StatusDots(full=full, total=total),
    )


@dataclass(frozen=True)
class StatusDots:
    full: int
    total: int
    symbol: str = "●"
    empty_symbol: str | None = None
    max_visible: int = 20


@dataclass(frozen=True)
class StatusContribution:
    key: str
    zone: StatusZone
    priority: int
    kind: StatusKind = StatusKind.TEXT
    content: object = ""
    style: str | None = None


@dataclass(frozen=True)
class StatusZoneRender:
    segments: tuple[StatusSegment, ...]
    text: str


@dataclass(frozen=True)
class StatusRender:
    left: StatusZoneRender
    center: StatusZoneRender
    right: StatusZoneRender


def render_text(content: object, tag: str = "normal") -> tuple[StatusSegment, ...]:
    text = str(content) if content is not None else ""
    if not text:
        return ()
    return (StatusSegment(text, tag),)


def render_filepath(filepath: StatusFilePath) -> tuple[StatusSegment, ...]:
    if filepath.fixed_colour and filepath.fixed_path:
        if filepath.label_path.startswith(filepath.fixed_path):
            fixed_portion = filepath.fixed_path
            remaining_portion = filepath.label_path[len(filepath.fixed_path) :]
        else:
            fixed_portion = ""
            remaining_portion = filepath.label_path

        return (
            StatusSegment(fixed_portion, "fixed"),
            StatusSegment(remaining_portion, "normal"),
        )

    return (StatusSegment(filepath.label_path, "normal"),)


def format_status_time(milliseconds: int | None) -> str:
    if milliseconds is None or milliseconds < 0:
        return "--:--"

    total_seconds = milliseconds // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def render_timer(timer: StatusTimer) -> tuple[StatusSegment, ...]:
    current_text = format_status_time(timer.current_ms)
    duration_text = format_status_time(timer.duration_ms)
    parts = [timer.label, f"{current_text} / {duration_text}"]
    if timer.paused:
        parts.append("PAUSED")
    if timer.status_text:
        parts.append(timer.status_text)
    return (StatusSegment(f"{timer.prefix}{' '.join(parts)}{timer.suffix}", "timer"),)


def render_dots(dots: StatusDots) -> tuple[StatusSegment, ...]:
    total = max(0, dots.total)
    full = max(0, min(dots.full, total))
    max_visible = max(0, dots.max_visible)
    visible_total = min(total, max_visible)
    visible_full = min(full, visible_total)
    visible_empty = visible_total - visible_full
    overflow = total - visible_total

    segments: list[StatusSegment] = []
    if visible_full:
        segments.append(StatusSegment(dots.symbol * visible_full, "dot-full"))
    if visible_empty:
        empty_symbol = dots.empty_symbol if dots.empty_symbol is not None else dots.symbol
        segments.append(StatusSegment(empty_symbol * visible_empty, "dot-empty"))
    if overflow:
        segments.append(StatusSegment(f"+{overflow}", "dot-overflow"))
    return tuple(segments)


def render_graph_stub() -> tuple[StatusSegment, ...]:
    return ()


def render_contribution(contribution: StatusContribution) -> tuple[StatusSegment, ...]:
    if contribution.kind == StatusKind.TEXT:
        return render_text(contribution.content, contribution.style or "normal")
    if contribution.kind == StatusKind.FILEPATH:
        if isinstance(contribution.content, StatusFilePath):
            return render_filepath(contribution.content)
        return ()
    if contribution.kind == StatusKind.TIMER:
        if isinstance(contribution.content, StatusTimer):
            return render_timer(contribution.content)
        return ()
    if contribution.kind == StatusKind.DOTS:
        if isinstance(contribution.content, StatusDots):
            return render_dots(contribution.content)
        return ()
    if contribution.kind == StatusKind.GRAPH:
        return render_graph_stub()
    return ()


def sort_contributions(
    contributions: list[StatusContribution] | tuple[StatusContribution, ...],
    zone: StatusZone,
) -> tuple[StatusContribution, ...]:
    zone_contributions = [
        contribution
        for contribution in contributions
        if contribution.zone == zone
    ]
    reverse = zone in (StatusZone.LEFT, StatusZone.CENTER)
    return tuple(
        sorted(
            zone_contributions,
            key=lambda contribution: (contribution.priority, contribution.key),
            reverse=reverse,
        )
    )


def render_zone(
    contributions: list[StatusContribution] | tuple[StatusContribution, ...],
    zone: StatusZone,
) -> StatusZoneRender:
    segments: list[StatusSegment] = []
    for contribution in sort_contributions(contributions, zone):
        contribution_segments = render_contribution(contribution)
        if not contribution_segments:
            continue
        if segments:
            segments.append(StatusSegment(" ", "separator"))
        segments.extend(contribution_segments)

    rendered_segments = tuple(segments)
    return StatusZoneRender(
        segments=rendered_segments,
        text="".join(segment.text for segment in rendered_segments),
    )


def render_status(
    contributions: list[StatusContribution] | tuple[StatusContribution, ...],
) -> StatusRender:
    return StatusRender(
        left=render_zone(contributions, StatusZone.LEFT),
        center=render_zone(contributions, StatusZone.CENTER),
        right=render_zone(contributions, StatusZone.RIGHT),
    )


def _count_text(
    current_image_path: str | None,
    image_paths: list[str],
    current_image_index: int,
) -> str:
    count = len(image_paths)
    if count <= 0:
        return "(0/0)"
    if current_image_path in image_paths:
        return f"({image_paths.index(current_image_path) + 1}/{count})"
    idx = max(1, min(current_image_index + 1, count))
    return f"({idx}/{count})"


def build_status_display(
    contributions: list[StatusContribution] | tuple[StatusContribution, ...],
) -> StatusDisplay:
    filename_segments: list[StatusSegment] = []
    fixed_colour = "white"
    for contribution in sort_contributions(contributions, StatusZone.LEFT):
        if (
            contribution.kind == StatusKind.FILEPATH
            and isinstance(contribution.content, StatusFilePath)
        ):
            fixed_colour = contribution.content.fixed_colour or "white"
        filename_segments.extend(render_contribution(contribution))

    rendered_filename_segments = tuple(filename_segments)
    filename_display = FilenameDisplay(
        segments=rendered_filename_segments,
        fixed_colour=fixed_colour,
        width=len("".join(segment.text for segment in rendered_filename_segments)) + 10,
    )
    return StatusDisplay(
        filename=filename_display,
        center=render_zone(contributions, StatusZone.CENTER),
        right=render_zone(contributions, StatusZone.RIGHT),
    )
