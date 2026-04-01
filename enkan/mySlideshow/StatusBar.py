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
    current_image_path: str | None
    image_paths: list[str]
    current_image_index: int
    provider_name: str
    provider_enabled: bool
    subfolder_mode: bool
    parent_mode: bool
    auto_advance_running: bool
    auto_advance_interval: int | float | None
    crw_display_mode: str
    crw_metrics: dict[str, float | int | str] | None


def provider_display_name(provider_name: str) -> str:
    labels = {
        "random": "RND",
        "weighted": "WGT",
        "controlled_random_weighted": "CRW",
        "sequential": "SEQ",
        "burst": "BUR",
    }
    return labels.get(provider_name, provider_name[0:3].upper())


def crw_status_text(
    display_mode: str,
    metrics: dict[str, float | int | str] | None,
) -> str:
    if display_mode == "off" or metrics is None:
        return ""

    age = int(metrics["age"])
    seen_before = bool(metrics["seen_before"])
    streak_len = int(metrics["streak_len"])
    bias_pct = float(metrics["bias_pct"])
    folder_factor = float(metrics["folder_factor"])
    boost = float(metrics["boost"])
    streak_factor = float(metrics["streak_factor"])
    combined = float(metrics["combined"])

    if display_mode == "friendly":
        if not seen_before:
            return "NEW"
        if combined >= 1.75:
            return "DUE"
        if combined >= 1.15:
            return "WARM"
        if folder_factor < 0.75:
            return "COOLING"
        return "NEUTRAL"

    if display_mode == "useful":
        if not seen_before:
            return f"NEW S{streak_len} B{bias_pct:+.0f}%"
        return f"A{age} S{streak_len} B{bias_pct:+.0f}%"

    if not seen_before:
        return (
            f"NEW S{streak_len} F{folder_factor:.2f} U{boost:.2f} T{streak_factor:.2f} "
            f"X{combined:.2f} B{bias_pct:+.0f}%"
        )
    return (
        f"A{age} S{streak_len} F{folder_factor:.2f} U{boost:.2f} T{streak_factor:.2f} "
        f"X{combined:.2f} B{bias_pct:+.0f}%"
    )


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

    meta_text = f" ({context.rotation_text}, {context.zoom_percent}%)"
    segments = (*segments, StatusSegment(meta_text, "meta"))
    width = len("".join(segment.text for segment in segments)) + 10
    return FilenameDisplay(
        segments=segments,
        fixed_colour=fixed_colour,
        width=width,
    )


def build_mode_text(context: StatusBarContext) -> str:
    provider_label = provider_display_name(context.provider_name) if context.provider_enabled else "-"
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

    crw_text = crw_status_text(context.crw_display_mode, context.crw_metrics)
    mode_parts = [count_text]
    if crw_text:
        mode_parts.append(crw_text)
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
