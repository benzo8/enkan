from enkan.mySlideshow.StatusBar import (
    StatusContribution,
    StatusDots,
    StatusFilePath,
    StatusKind,
    StatusTimer,
    StatusZone,
    AUTO_ADVANCE_STATUS_KEY,
    CACHE_DOTS_STATUS_KEY,
    COUNT_STATUS_KEY,
    PROVIDER_BURST_DOTS_STATUS_KEY,
    PROVIDER_DETAIL_STATUS_KEY,
    PROVIDER_LABEL_STATUS_KEY,
    RUNTIME_STATUS_KEY,
    SCOPE_STATUS_KEY,
    StatusBar,
    build_auto_advance_contribution,
    build_cache_dots_contribution,
    build_count_contribution,
    build_filepath_contribution,
    build_image_meta_contribution,
    build_video_timer_contribution,
    build_provider_burst_dots_contribution,
    build_provider_detail_contribution,
    build_provider_label_contribution,
    build_runtime_status_contribution,
    build_scope_contribution,
    build_status_display,
    render_contribution,
    render_dots,
    render_status,
    render_timer,
)


def test_status_display_renders_image_status_contributions():
    display = build_status_display(
        (
            build_filepath_contribution(
                "root\\folder\\image.jpg",
                "root\\folder",
                "gold",
            ),
            build_image_meta_contribution("90°", 125),
            build_auto_advance_contribution(True, 5000),
            build_count_contribution(
                "root\\folder\\image.jpg",
                ["root\\folder\\image.jpg", "root\\folder\\two.jpg"],
                0,
            ),
            build_scope_contribution(True, False),
            build_provider_detail_contribution("A7"),
            build_provider_label_contribution("CRW"),
        )
    )

    assert [segment.text for segment in display.filename.segments] == [
        "root\\folder",
        "\\image.jpg",
        " (90°, 125%)",
    ]
    assert display.filename.fixed_colour == "gold"
    assert display.mode_text == "AUTO (5000ms)   (1/2) SUB A7 CRW"


def test_status_display_renders_video_timer_contributions():
    display = build_status_display(
        (
            build_filepath_contribution("clip.mp4", None, None),
            build_video_timer_contribution(
                current_ms=65_000,
                duration_ms=125_000,
                paused=True,
                status_text="",
            ),
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


def test_status_display_renders_video_unknown_timing():
    display = build_status_display(
        (
            build_filepath_contribution("clip.mp4", None, None),
            build_video_timer_contribution(
                current_ms=None,
                duration_ms=None,
                paused=False,
                status_text="buffering",
            )
        )
    )

    assert [segment.text for segment in display.filename.segments] == [
        "clip.mp4",
        " { VIDEO --:-- / --:-- BUFFERING }",
    ]


def test_runtime_status_contribution_uses_stable_key():
    contribution = build_runtime_status_contribution("No displayable media")

    assert contribution.key == RUNTIME_STATUS_KEY
    assert contribution.content == "No displayable media"


def test_auto_advance_contribution_uses_stable_key_and_clears_when_stopped():
    contribution = build_auto_advance_contribution(True, 5000)

    assert contribution is not None
    assert contribution.key == AUTO_ADVANCE_STATUS_KEY
    assert contribution.content == "AUTO (5000ms)  "
    assert build_auto_advance_contribution(False, 5000) is None


def test_cache_dots_contribution_renders_in_center_zone():
    display = build_status_display((build_cache_dots_contribution(2, 3),))

    assert display.center_text == "●●●"
    assert display.mode_text == ""


def test_provider_contributions_render_label_detail_and_burst_dots_in_order():
    display = build_status_display(
        (
            build_provider_detail_contribution("BB NEW"),
            build_provider_label_contribution("BUR"),
            build_provider_burst_dots_contribution(2, 5),
        )
    )

    assert display.mode_text == "BB NEW ●●●●● BUR"


def test_provider_contribution_keys_are_stable():
    assert build_provider_label_contribution("WGT").key == PROVIDER_LABEL_STATUS_KEY
    assert build_provider_detail_contribution("BB NEW").key == PROVIDER_DETAIL_STATUS_KEY
    assert (
        build_provider_burst_dots_contribution(1, 3).key
        == PROVIDER_BURST_DOTS_STATUS_KEY
    )


def test_provider_burst_dots_keep_stable_text_width_with_empty_colour():
    contribution = build_provider_burst_dots_contribution(2, 5)

    assert render_contribution(contribution)[0].text == "●●"
    assert render_contribution(contribution)[1].text == "●●●"
    assert render_contribution(contribution)[1].tag == "dot-empty"


def test_provider_burst_dots_do_not_change_generic_cache_dot_rendering():
    cache_segments = render_contribution(build_cache_dots_contribution(2, 5))
    burst_segments = render_contribution(build_provider_burst_dots_contribution(2, 5))

    assert [(segment.text, segment.tag) for segment in cache_segments] == [
        ("●●", "dot-full"),
        ("●●●", "dot-empty"),
    ]
    assert [(segment.text, segment.tag) for segment in burst_segments] == [
        ("●●", "dot-full"),
        ("●●●", "dot-empty"),
    ]


def test_count_contribution_uses_stable_key_and_index_fallback():
    contribution = build_count_contribution(
        current_image_path="outside.jpg",
        image_paths=["one.jpg", "two.jpg"],
        current_image_index=9,
    )

    assert contribution.key == COUNT_STATUS_KEY
    assert contribution.content == "(2/2)"


def test_scope_contribution_uses_stable_key_and_clears_when_empty():
    contribution = build_scope_contribution(True, True)

    assert contribution is not None
    assert contribution.key == SCOPE_STATUS_KEY
    assert contribution.content == "SUB PAR"
    assert build_scope_contribution(False, False) is None


def test_status_bar_set_contribution_refreshes_visible_display():
    status_bar = StatusBar.__new__(StatusBar)
    updates = []
    status_bar._visible = True
    status_bar._base_contributions = {
        "filepath": StatusContribution(
            "filepath",
            StatusZone.LEFT,
            100,
            kind=StatusKind.FILEPATH,
            content=StatusFilePath("clip.mp4"),
        )
    }
    status_bar._owned_contributions = {}
    status_bar.update = lambda display, visible: updates.append((display, visible))

    status_bar.set_contribution(
        StatusContribution(
            "video-timer",
            StatusZone.LEFT,
            90,
            kind=StatusKind.TIMER,
            content=StatusTimer(1_000, 2_000),
        )
    )

    assert updates[-1][1] is True
    assert [segment.text for segment in updates[-1][0].filename.segments] == [
        "clip.mp4",
        "VIDEO 00:01 / 00:02",
    ]


def test_status_bar_hidden_contribution_is_retained_until_visible():
    status_bar = StatusBar.__new__(StatusBar)
    hidden_calls = []
    updates = []
    status_bar.root = type(
        "_Root",
        (),
        {"update_idletasks": lambda self: hidden_calls.append("idle")},
    )()
    status_bar.hide = lambda: hidden_calls.append("hide")
    status_bar.update = lambda display, visible: updates.append((display, visible))
    status_bar._visible = False
    status_bar._base_contributions = {}
    status_bar._owned_contributions = {}

    status_bar.set_contribution(
        StatusContribution("runtime-status", StatusZone.RIGHT, 30, content="VIDEO: failed")
    )
    status_bar.set_base_contributions(
        (
            StatusContribution(
                "filepath",
                StatusZone.LEFT,
                100,
                kind=StatusKind.FILEPATH,
                content=StatusFilePath("clip.mp4"),
            ),
        ),
        visible=True,
    )

    assert updates[-1][0].mode_text == "VIDEO: failed"
    assert hidden_calls == ["hide", "idle"]


def test_status_bar_contribution_visibility_hides_and_restores_data():
    status_bar = StatusBar.__new__(StatusBar)
    updates = []
    status_bar._visible = True
    status_bar._base_contributions = {}
    status_bar._owned_contributions = {}
    status_bar._hidden_contribution_keys = set()
    status_bar.update = lambda display, visible: updates.append((display, visible))

    status_bar.set_contribution(build_cache_dots_contribution(2, 3))
    status_bar.set_contribution_visible(CACHE_DOTS_STATUS_KEY, False)
    status_bar.set_contribution(build_cache_dots_contribution(3, 3))
    status_bar.set_contribution_visible(CACHE_DOTS_STATUS_KEY, True)

    assert updates[0][0].center_text == "●●●"
    assert updates[1][0].center_text == ""
    assert updates[2][0].center_text == ""
    assert updates[3][0].center_text == "●●●"


def test_status_bar_clear_contribution_refreshes_without_clearing_base_status():
    status_bar = StatusBar.__new__(StatusBar)
    updates = []
    status_bar._visible = True
    status_bar._base_contributions = {
        "filepath": StatusContribution(
            "filepath",
            StatusZone.LEFT,
            100,
            kind=StatusKind.FILEPATH,
            content=StatusFilePath("clip.mp4"),
        )
    }
    status_bar._owned_contributions = {
        "runtime-status": StatusContribution(
            "runtime-status",
            StatusZone.RIGHT,
            30,
            content="VIDEO: failed",
        )
    }
    status_bar.update = lambda display, visible: updates.append((display, visible))

    status_bar.clear_contribution("runtime-status")

    assert updates[-1][0].mode_text == ""
    assert [segment.text for segment in updates[-1][0].filename.segments] == ["clip.mp4"]


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
        ("●●●", "dot-full"),
        ("●●", "dot-empty"),
        ("+1", "dot-overflow"),
    ]


def test_render_dots_clamps_full_count():
    segments = render_dots(StatusDots(full=8, total=3, max_visible=5))

    assert [(segment.text, segment.tag) for segment in segments] == [
        ("●●●", "dot-full"),
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
