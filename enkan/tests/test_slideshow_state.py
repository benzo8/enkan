from enkan.mySlideshow.mySlideshow import ImageSlideshow


def test_safe_current_image_index_uses_current_path_when_present():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.current_image_path = "b.jpg"
    slideshow.current_image_index = 0

    assert slideshow.safe_current_image_index(["a.jpg", "b.jpg", "c.jpg"]) == 1


def test_safe_current_image_index_prefers_surviving_neighbor_after_deletion():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.current_image_path = "b.jpg"
    slideshow.current_image_index = 1

    assert slideshow.safe_current_image_index(["a.jpg", "c.jpg"], preferred_index=1) == 1


def test_safe_current_image_index_handles_empty_image_list():
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.current_image_path = "gone.jpg"
    slideshow.current_image_index = 4

    assert slideshow.safe_current_image_index([]) == 0
