from dataclasses import dataclass


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


def build_filename_display(context: StatusBarContext) -> FilenameDisplay:
    fixed_colour = context.fixed_colour or "white"
    if context.fixed_colour and context.fixed_path:
        if context.label_path.startswith(context.fixed_path):
            fixed_portion = context.fixed_path
            remaining_portion = context.label_path[len(context.fixed_path) :]
        else:
            fixed_portion = ""
            remaining_portion = context.label_path

        segments = (
            StatusSegment(fixed_portion, "fixed"),
            StatusSegment(remaining_portion, "normal"),
        )
    else:
        segments = (StatusSegment(context.label_path, "normal"),)

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
