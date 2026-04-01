from enkan.plugables.ImageProviders import ImageProviders


def test_image_providers_returns_current_provider_label():
    providers = ImageProviders()
    providers.current_provider_name = "controlled_random_weighted"

    assert providers.get_current_provider_label() == "CRW"


def test_image_providers_returns_empty_status_for_non_crw():
    providers = ImageProviders()
    providers.current_provider_name = "weighted"

    assert providers.get_current_provider_status(
        display_mode="debug",
        status_payload={"age": 5},
    ) == ""


def test_image_providers_formats_crw_provider_status():
    providers = ImageProviders()
    providers.current_provider_name = "controlled_random_weighted"

    text = providers.get_current_provider_status(
        display_mode="friendly",
        status_payload={
            "age": 5,
            "seen_before": False,
            "streak_len": 0,
            "folder_factor": 1.0,
            "boost": 1.0,
            "streak_factor": 1.0,
            "combined": 1.0,
            "bias_pct": 0.0,
        },
    )

    assert text == "NEW"
