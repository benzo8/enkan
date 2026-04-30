from enkan.mySlideshow.StatusBar import (
    StatusContribution,
    StatusDots,
    StatusFilePath,
    StatusKind,
    StatusTimer,
    StatusZone,
    StatusBarContext,
    build_filename_display,
    build_mode_text,
    build_status_contributions,
    build_status_display,
    render_contribution,
    render_dots,
    render_status,
    render_timer,
)


def _context(**overrides) -> StatusBarContext:
    base = dict(
        label_path="root\\folder\\image.jpg",
        fixed_path=None,
        fixed_colour=None,
        rotation_text="0°",
        zoom_percent=100,
        filename_meta_text=None,
        current_image_path="root\\folder\\image.jpg",
        image_paths=["root\\folder\\image.jpg", "root\\folder\\two.jpg"],
        current_image_index=0,
        provider_enabled=True,
        provider_label="WGT",
        provider_status_text="",
        runtime_status_text="",
        subfolder_mode=False,
        parent_mode=False,
        auto_advance_running=False,
        auto_advance_interval=None,
    )
    base.update(overrides)
    return StatusBarContext(**base)


def test_build_filename_display_splits_fixed_and_normal_segments():
    display = build_filename_display(
        _context(
            fixed_path="root\\folder",
            fixed_colour="gold",
        )
    )

    assert [segment.text for segment in display.segments] == [
        "root\\folder",
        "\\image.jpg",
        " (0°, 100%)",
    ]
    assert display.fixed_colour == "gold"


def test_build_filename_display_uses_filename_meta_override():
    display = build_filename_display(
        _context(filename_meta_text=" { VIDEO 00:05 / 01:00 PAUSED }")
    )

    assert [segment.text for segment in display.segments] == [
        "root\\folder\\image.jpg",
        " { VIDEO 00:05 / 01:00 PAUSED }",
    ]


def test_build_mode_text_includes_scope_and_provider():
    text = build_mode_text(
        _context(
            provider_label="CRW",
            provider_status_text="A7 S2 B-10%",
            subfolder_mode=True,
            parent_mode=True,
        )
    )

    assert text == "(1/2) A7 S2 B-10% SUB PAR CRW"


def test_build_mode_text_includes_runtime_status():
    text = build_mode_text(
        _context(
            provider_label="CRW",
            provider_status_text="A7",
            runtime_status_text="VIDEO: failed",
            subfolder_mode=True,
        )
    )

    assert text == "(1/2) A7 VIDEO: failed SUB CRW"


def test_build_mode_text_prefixes_auto_advance():
    text = build_mode_text(
        _context(
            auto_advance_running=True,
            auto_advance_interval=5000,
        )
    )

    assert text == "AUTO (5000ms)   (1/2) WGT"


def test_status_contributions_reproduce_image_status_display():
    display = build_status_display(
        build_status_contributions(
            label_path="root\\folder\\image.jpg",
            fixed_path="root\\folder",
            fixed_colour="gold",
            rotation_text="90°",
            zoom_percent=125,
            is_video=False,
            video_current_ms=None,
            video_duration_ms=None,
            video_paused=False,
            video_status_text="",
            current_image_path="root\\folder\\image.jpg",
            image_paths=["root\\folder\\image.jpg", "root\\folder\\two.jpg"],
            current_image_index=0,
            provider_enabled=True,
            provider_label="CRW",
            provider_status_text="A7",
            runtime_status_text="",
            subfolder_mode=True,
            parent_mode=False,
            auto_advance_running=True,
            auto_advance_interval=5000,
        )
    )

    assert [segment.text for segment in display.filename.segments] == [
        "root\\folder",
        "\\image.jpg",
        " (90°, 125%)",
    ]
    assert display.filename.fixed_colour == "gold"
    assert display.mode_text == "AUTO (5000ms)   (1/2) A7 SUB CRW"


def test_status_contributions_reproduce_video_timer_display():
    display = build_status_display(
        build_status_contributions(
            label_path="clip.mp4",
            fixed_path=None,
            fixed_colour=None,
            rotation_text="0°",
            zoom_percent=100,
            is_video=True,
            video_current_ms=65_000,
            video_duration_ms=125_000,
            video_paused=True,
            video_status_text="",
            current_image_path="clip.mp4",
            image_paths=["clip.mp4"],
            current_image_index=0,
            provider_enabled=True,
            provider_label="WGT",
            provider_status_text="",
            runtime_status_text="",
            subfolder_mode=False,
            parent_mode=False,
            auto_advance_running=False,
            auto_advance_interval=None,
        )
    )

    assert [segment.text for segment in display.filename.segments] == [
        "clip.mp4",
        " { VIDEO 01:05 / 02:05 PAUSED }",
    ]
    assert [segment.tag for segment in display.filename.segments] == [
        "normal",
        "timer",
    ]


def test_render_status_orders_left_and_center_from_left_edge():
    rendered = render_status(
        (
            StatusContribution("left-low", StatusZone.LEFT, 1, content="low"),
            StatusContribution("left-high", StatusZone.LEFT, 10, content="high"),
            StatusContribution("center-low", StatusZone.CENTER, 1, content="C-low"),
            StatusContribution("center-high", StatusZone.CENTER, 10, content="C-high"),
        )
    )

    assert rendered.left.text == "high low"
    assert rendered.center.text == "C-high C-low"


def test_render_status_orders_right_from_right_edge():
    rendered = render_status(
        (
            StatusContribution("right-low", StatusZone.RIGHT, 1, content="low"),
            StatusContribution("right-high", StatusZone.RIGHT, 10, content="high"),
        )
    )

    assert rendered.right.text == "low high"


def test_render_filepath_segments_fixed_prefix():
    segments = render_contribution(
        StatusContribution(
            "path",
            StatusZone.LEFT,
            1,
            kind=StatusKind.FILEPATH,
            content=StatusFilePath(
                label_path="root\\folder\\image.jpg",
                fixed_path="root\\folder",
                fixed_colour="gold",
            ),
        )
    )

    assert [(segment.text, segment.tag) for segment in segments] == [
        ("root\\folder", "fixed"),
        ("\\image.jpg", "normal"),
    ]


def test_render_timer_formats_time_and_state():
    segments = render_timer(
        StatusTimer(
            current_ms=65_000,
            duration_ms=3_665_000,
            paused=True,
            status_text="BUFFERING",
        )
    )

    assert segments[0].text == "VIDEO 01:05 / 1:01:05 PAUSED BUFFERING"
    assert segments[0].tag == "timer"


def test_render_timer_handles_unknown_times():
    segments = render_timer(StatusTimer(current_ms=None, duration_ms=-1))

    assert segments[0].text == "VIDEO --:-- / --:--"


def test_render_dots_caps_visible_dots_and_marks_overflow():
    segments = render_dots(StatusDots(full=3, total=6, max_visible=5))

    assert [(segment.text, segment.tag) for segment in segments] == [
        ("・・・", "dot-full"),
        ("・・", "dot-empty"),
        ("+1", "dot-overflow"),
    ]


def test_render_dots_clamps_full_count():
    segments = render_dots(StatusDots(full=8, total=3, max_visible=5))

    assert [(segment.text, segment.tag) for segment in segments] == [
        ("・・・", "dot-full"),
    ]


def test_graph_contribution_is_stubbed_empty():
    segments = render_contribution(
        StatusContribution(
            "graph",
            StatusZone.RIGHT,
            1,
            kind=StatusKind.GRAPH,
            content=None,
        )
    )

    assert segments == ()
