from enkan.mySlideshow.StatusBar import (
    StatusBarContext,
    build_filename_display,
    build_mode_text,
)


def _context(**overrides) -> StatusBarContext:
    base = dict(
        label_path="root\\folder\\image.jpg",
        fixed_path=None,
        fixed_colour=None,
        rotation_text="0°",
        zoom_percent=100,
        current_image_path="root\\folder\\image.jpg",
        image_paths=["root\\folder\\image.jpg", "root\\folder\\two.jpg"],
        current_image_index=0,
        provider_enabled=True,
        provider_label="WGT",
        provider_status_text="",
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


def test_build_mode_text_prefixes_auto_advance():
    text = build_mode_text(
        _context(
            auto_advance_running=True,
            auto_advance_interval=5000,
        )
    )

    assert text == "AUTO (5000ms)   (1/2) WGT"
