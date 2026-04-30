from enkan.mySlideshow.StatusBar import IMAGE_META_STATUS_KEY
from enkan.mySlideshow.ZoomPan import ZoomPan


class _Sink:
    def __init__(self):
        self.contributions = []
        self.cleared = []

    def set_contribution(self, contribution):
        self.contributions.append(contribution)

    def set_contributions(self, contributions):
        self.contributions.extend(contributions)

    def clear_contribution(self, key):
        self.cleared.append(key)


def _zoompan(**overrides):
    zoompan = ZoomPan.__new__(ZoomPan)
    base = dict(
        status_sink=_Sink(),
        orig_image=object(),
        source_image=object(),
        current_exif_orientation=1,
        rotation_angle=0,
        zoom_factor=1.0,
    )
    base.update(overrides)
    for key, value in base.items():
        setattr(zoompan, key, value)
    return zoompan


def test_rotation_display_text_combines_exif_and_manual_rotation():
    zoompan = _zoompan(current_exif_orientation=6, rotation_angle=270)

    assert zoompan.rotation_display_text() == "180°"


def test_rotation_display_text_marks_unmodified_exif_rotation():
    zoompan = _zoompan(current_exif_orientation=6, rotation_angle=0)

    assert zoompan.rotation_display_text() == "90° [EXIF]"


def test_publish_image_meta_status_uses_zoom_and_rotation():
    sink = _Sink()
    zoompan = _zoompan(
        status_sink=sink,
        current_exif_orientation=1,
        rotation_angle=270,
        zoom_factor=1.25,
    )

    zoompan.publish_image_meta_status()

    assert sink.contributions[-1].key == IMAGE_META_STATUS_KEY
    assert sink.contributions[-1].content == " (90°, 125%)"


def test_clear_image_clears_image_meta_status():
    sink = _Sink()
    zoompan = _zoompan(status_sink=sink)
    zoompan.photo = object()

    zoompan.clear_image()

    assert zoompan.orig_image is None
    assert zoompan.source_image is None
    assert zoompan.photo is None
    assert sink.cleared == [IMAGE_META_STATUS_KEY]
