from types import SimpleNamespace

from enkan.mySlideshow.VideoTransportOverlay import VideoTransportOverlay


def test_video_transport_overlay_formats_times():
    assert VideoTransportOverlay._format_time(None) == "--:--"
    assert VideoTransportOverlay._format_time(65_000) == "1:05"
    assert VideoTransportOverlay._format_time(3_665_000) == "1:01:05"


def test_video_transport_overlay_reveals_only_when_active_near_bottom():
    overlay = VideoTransportOverlay.__new__(VideoTransportOverlay)
    overlay._active = False
    overlay.REVEAL_EDGE_PX = 80
    overlay.root = SimpleNamespace(winfo_height=lambda: 500)
    shown: list[str] = []
    overlay.show = lambda: shown.append("show")

    overlay.handle_motion(SimpleNamespace(y=460))
    assert shown == []

    overlay._active = True
    overlay.handle_motion(SimpleNamespace(y=300))
    assert shown == []

    overlay.handle_motion(SimpleNamespace(y=460))
    assert shown == ["show"]
