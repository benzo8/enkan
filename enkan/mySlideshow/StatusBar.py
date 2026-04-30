from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class StatusSegment:
    text: str
    tag: str


@dataclass(frozen=True)
class FilenameDisplay:
    segments: tuple[StatusSegment, ...]
    fixed_colour: str
    width: int


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
    return (StatusSegment(" ".join(parts), "timer"),)


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


def build_filename_display(context: StatusBarContext) -> FilenameDisplay:
    fixed_colour = context.fixed_colour or "white"
    segments = render_filepath(
        StatusFilePath(
            label_path=context.label_path,
            fixed_path=context.fixed_path,
            fixed_colour=context.fixed_colour,
        )
    )
    meta_text = (
        context.filename_meta_text
        if context.filename_meta_text is not None
        else f" ({context.rotation_text}, {context.zoom_percent}%)"
    )
    segments = (*segments, StatusSegment(meta_text, "meta"))
    width = len("".join(segment.text for segment in segments)) + 10
    return FilenameDisplay(
        segments=segments,
        fixed_colour=fixed_colour,
        width=width,
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
