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


def test_image_providers_builds_crw_status_payload():
    providers = ImageProviders()
    providers.current_provider_name = "controlled_random_weighted"

    class _FolderMemory:
        def has_seen(self, folder):
            return True

        def distance_for(self, folder):
            return 7

        def streak_for(self, folder):
            return 2

    payload = providers.get_current_provider_status_payload(
        image_paths=["root\\a\\one.jpg", "root\\b\\two.jpg"],
        weights=[2.0, 1.0],
        current_image_path="root\\a\\one.jpg",
        folder_memory=_FolderMemory(),
        settings={
            "gap_min": 3,
            "gap_max": 10,
            "alpha": 0.01,
            "repeat_penalty": 0.1,
        },
    )

    assert payload is not None
    assert payload["folder"] == "root\\a"
    assert payload["seen_before"] is True
    assert payload["streak_len"] == 2


def test_image_providers_returns_controlled_random_settings():
    providers = ImageProviders()

    settings = providers.get_controlled_random_settings(
        image_paths=["root\\a\\one.jpg", "root\\b\\two.jpg"],
        weights=[2.0, 1.0],
        gap_min=3,
        repeat_penalty=0.2,
    )

    assert settings["gap_min"] == 3
    assert settings["repeat_penalty"] == 0.2
    assert settings["gap_max"] >= 4


def test_image_providers_recomputes_crw_settings_on_same_provider_rebuild(monkeypatch):
    providers = ImageProviders()
    providers.register_provider(
        "controlled_random_weighted",
        lambda image_paths, **kwargs: iter(()),
    )

    monkeypatch.setattr(
        "enkan.plugables.ImageProviders.ImageCacheManager",
        lambda image_provider, current_image_index, background_preload=True: object(),
    )

    providers.select_manager(
        ["root\\a\\one.jpg", "root\\b\\two.jpg"],
        provider_name="controlled_random_weighted",
        weights=[1.0, 1.0],
        gap_min=5,
        repeat_penalty=0.2,
    )
    initial_settings = providers.get_current_provider_settings()

    providers.select_manager(
        [f"root\\{i}\\file.jpg" for i in range(20)],
        provider_name="controlled_random_weighted",
        weights=[1.0] * 20,
    )
    rebuilt_settings = providers.get_current_provider_settings()

    assert rebuilt_settings["gap_min"] == 5
    assert rebuilt_settings["repeat_penalty"] == 0.2
    assert rebuilt_settings["gap_max"] > initial_settings["gap_max"]


def test_image_providers_cycles_display_mode_for_current_provider():
    providers = ImageProviders()
    providers.current_provider_name = "controlled_random_weighted"

    assert providers.get_current_provider_display_mode() == "off"
    assert providers.cycle_current_provider_display_mode() == "friendly"
    assert providers.cycle_current_provider_display_mode() == "useful"


def test_image_providers_preserves_display_mode_when_rebuilding_same_provider(monkeypatch):
    providers = ImageProviders()
    providers.register_provider("test_provider", lambda image_paths, **kwargs: iter(()))
    providers.current_provider_name = "test_provider"
    providers.provider_display_modes["test_provider"] = ("off", "detail", "debug")
    providers.current_provider_display_mode_index = 2

    monkeypatch.setattr(
        "enkan.plugables.ImageProviders.ImageCacheManager",
        lambda image_provider, current_image_index, background_preload=True: object(),
    )

    providers.select_manager([], provider_name="test_provider")

    assert providers.get_current_provider_display_mode() == "debug"
