from dataclasses import dataclass
from enum import Enum
import tkinter as tk
from typing import Protocol


VIDEO_TIMER_STATUS_KEY = "video-timer"
VIDEO_RUNTIME_STATUS_KEY = "video-runtime-status"


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
    mode_text: str


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
        self._visible = False
        self._base_contributions: dict[str, StatusContribution] = {}
        self._owned_contributions: dict[str, StatusContribution] = {}
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
        self.mode_label = tk.Label(root, bg="black", fg="white", anchor="ne")

    def raise_widgets(self) -> None:
        self.filename_label.tkraise()
        self.mode_label.tkraise()

    def hide(self) -> None:
        self.filename_label.place_forget()
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
        self._owned_contributions[contribution.key] = contribution
        self._refresh_visible_status()

    def set_contributions(
        self,
        contributions: list["StatusContribution"] | tuple["StatusContribution", ...],
    ) -> None:
        for contribution in contributions:
            self._owned_contributions[contribution.key] = contribution
        self._refresh_visible_status()

    def clear_contribution(self, key: str) -> None:
        if key in self._owned_contributions:
            del self._owned_contributions[key]
            self._refresh_visible_status()

    def _merged_contributions(self) -> tuple["StatusContribution", ...]:
        merged = {
            **self._base_contributions,
            **self._owned_contributions,
        }
        return tuple(merged.values())

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
        self.filename_label.place(x=0, y=0)
        self.filename_label.config(height=1, width=filename_display.width, bg="black")
        self.filename_label.config(state=tk.DISABLED)

        self.mode_label.config(
            text=display.mode_text,
            fg="white",
        )
        self.mode_label.place(x=self.root.winfo_screenwidth(), y=0, anchor="ne")
        self.root.update_idletasks()


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


@dataclass(frozen=True)
class StatusDots:
    full: int
    total: int
    symbol: str = "・"
    full_colour: str = "green"
    empty_colour: str = "grey"
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


@dataclass(frozen=True)
class StatusBarContext:
    label_path: str
    fixed_path: str | None
    fixed_colour: str | None
    rotation_text: str
    zoom_percent: int
    filename_meta_text: str | None
    current_image_path: str | None
    image_paths: list[str]
    current_image_index: int
    provider_enabled: bool
    provider_label: str
    provider_status_text: str
    runtime_status_text: str
    subfolder_mode: bool
    parent_mode: bool
    auto_advance_running: bool
    auto_advance_interval: int | float | None


@dataclass(frozen=True)
class StatusFacts:
    label_path: str
    fixed_path: str | None
    fixed_colour: str | None
    rotation_text: str
    zoom_percent: int
    is_video: bool
    video_current_ms: int | None
    video_duration_ms: int | None
    video_paused: bool
    video_status_text: str
    current_image_path: str | None
    image_paths: list[str]
    current_image_index: int
    provider_enabled: bool
    provider_label: str
    provider_status_text: str
    runtime_status_text: str
    subfolder_mode: bool
    parent_mode: bool
    auto_advance_running: bool
    auto_advance_interval: int | float | None
    video_timer_from_sink: bool = False


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
        segments.append(StatusSegment(dots.symbol * visible_empty, "dot-empty"))
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


def build_status_contributions(
    *,
    label_path: str,
    fixed_path: str | None,
    fixed_colour: str | None,
    rotation_text: str,
    zoom_percent: int,
    is_video: bool,
    video_current_ms: int | None,
    video_duration_ms: int | None,
    video_paused: bool,
    video_status_text: str,
    current_image_path: str | None,
    image_paths: list[str],
    current_image_index: int,
    provider_enabled: bool,
    provider_label: str,
    provider_status_text: str,
    runtime_status_text: str,
    subfolder_mode: bool,
    parent_mode: bool,
    auto_advance_running: bool,
    auto_advance_interval: int | float | None,
) -> tuple[StatusContribution, ...]:
    return build_status_contributions_from_facts(
        StatusFacts(
            label_path=label_path,
            fixed_path=fixed_path,
            fixed_colour=fixed_colour,
            rotation_text=rotation_text,
            zoom_percent=zoom_percent,
            is_video=is_video,
            video_current_ms=video_current_ms,
            video_duration_ms=video_duration_ms,
            video_paused=video_paused,
            video_status_text=video_status_text,
            current_image_path=current_image_path,
            image_paths=image_paths,
            current_image_index=current_image_index,
            provider_enabled=provider_enabled,
            provider_label=provider_label,
            provider_status_text=provider_status_text,
            runtime_status_text=runtime_status_text,
            subfolder_mode=subfolder_mode,
            parent_mode=parent_mode,
            auto_advance_running=auto_advance_running,
            auto_advance_interval=auto_advance_interval,
            video_timer_from_sink=False,
        )
    )


def build_status_contributions_from_facts(
    facts: StatusFacts,
) -> tuple[StatusContribution, ...]:
    contributions: list[StatusContribution] = [
        StatusContribution(
            "filepath",
            StatusZone.LEFT,
            100,
            kind=StatusKind.FILEPATH,
            content=StatusFilePath(
                facts.label_path,
                facts.fixed_path,
                facts.fixed_colour,
            ),
        )
    ]

    if facts.is_video and not facts.video_timer_from_sink:
        contributions.append(
            build_video_timer_contribution(
                current_ms=facts.video_current_ms,
                duration_ms=facts.video_duration_ms,
                paused=facts.video_paused,
                status_text=facts.video_status_text,
            )
        )
    else:
        contributions.append(
            StatusContribution(
                "image-meta",
                StatusZone.LEFT,
                90,
                content=f" ({facts.rotation_text}, {facts.zoom_percent}%)",
                style="meta",
            )
        )

    if (
        facts.auto_advance_running
        and facts.auto_advance_interval is not None
        and facts.auto_advance_interval > 0
    ):
        contributions.append(
            StatusContribution(
                "auto-advance",
                StatusZone.RIGHT,
                0,
                content=f"AUTO ({facts.auto_advance_interval}ms)  ",
            )
        )

    contributions.append(
        StatusContribution(
            "count",
            StatusZone.RIGHT,
            10,
            content=_count_text(
                facts.current_image_path,
                facts.image_paths,
                facts.current_image_index,
            ),
        )
    )
    if facts.provider_status_text:
        contributions.append(
            StatusContribution(
                "provider-status",
                StatusZone.RIGHT,
                20,
                content=facts.provider_status_text,
            )
        )
    if facts.runtime_status_text:
        contributions.append(
            StatusContribution(
                "runtime-status",
                StatusZone.RIGHT,
                30,
                content=facts.runtime_status_text,
            )
        )
    scope_parts: list[str] = []
    if facts.subfolder_mode:
        scope_parts.append("SUB")
    if facts.parent_mode:
        scope_parts.append("PAR")
    if scope_parts:
        contributions.append(
            StatusContribution(
                "scope",
                StatusZone.RIGHT,
                40,
                content=" ".join(scope_parts),
            )
        )
    contributions.append(
        StatusContribution(
            "provider-label",
            StatusZone.RIGHT,
            100,
            content=facts.provider_label if facts.provider_enabled else "-",
        )
    )
    return tuple(contributions)


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
        mode_text=render_zone(contributions, StatusZone.RIGHT).text,
    )


def build_filename_display(context: StatusBarContext) -> FilenameDisplay:
    display = build_status_display(
        build_status_contributions(
            label_path=context.label_path,
            fixed_path=context.fixed_path,
            fixed_colour=context.fixed_colour,
            rotation_text=context.rotation_text,
            zoom_percent=context.zoom_percent,
            is_video=context.filename_meta_text is not None,
            video_current_ms=None,
            video_duration_ms=None,
            video_paused=False,
            video_status_text="",
            current_image_path=context.current_image_path,
            image_paths=context.image_paths,
            current_image_index=context.current_image_index,
            provider_enabled=context.provider_enabled,
            provider_label=context.provider_label,
            provider_status_text=context.provider_status_text,
            runtime_status_text=context.runtime_status_text,
            subfolder_mode=context.subfolder_mode,
            parent_mode=context.parent_mode,
            auto_advance_running=context.auto_advance_running,
            auto_advance_interval=context.auto_advance_interval,
        )
    )
    if context.filename_meta_text is None:
        return display.filename

    segments = render_filepath(
        StatusFilePath(context.label_path, context.fixed_path, context.fixed_colour)
    )
    segments = (*segments, StatusSegment(context.filename_meta_text, "meta"))
    return FilenameDisplay(
        segments=segments,
        fixed_colour=context.fixed_colour or "white",
        width=len("".join(segment.text for segment in segments)) + 10,
    )


def build_mode_text(context: StatusBarContext) -> str:
    provider_label = context.provider_label if context.provider_enabled else "-"
    scope_parts: list[str] = []
    if context.subfolder_mode:
        scope_parts.append("SUB")
    if context.parent_mode:
        scope_parts.append("PAR")

    count = len(context.image_paths)
    if count <= 0:
        count_text = "(0/0)"
    elif context.current_image_path in context.image_paths:
        count_text = f"({context.image_paths.index(context.current_image_path) + 1}/{count})"
    else:
        idx = max(1, min(context.current_image_index + 1, count))
        count_text = f"({idx}/{count})"

    mode_parts = [count_text]
    if context.provider_status_text:
        mode_parts.append(context.provider_status_text)
    if context.runtime_status_text:
        mode_parts.append(context.runtime_status_text)
    if scope_parts:
        mode_parts.append(" ".join(scope_parts))
    mode_parts.append(provider_label)
    mode_text = " ".join(mode_parts)

    if (
        context.auto_advance_running
        and context.auto_advance_interval is not None
        and context.auto_advance_interval > 0
    ):
        return f"AUTO ({context.auto_advance_interval}ms)   {mode_text}"
    return mode_text
