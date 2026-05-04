from __future__ import annotations

from argparse import Namespace

import pytest

from enkan.config import AppConfig, ConfigError, load_app_config, merge_config_into_args


def test_load_app_config_uses_defaults_when_default_file_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config = load_app_config()

    assert config.mode is None
    assert config.random is None
    assert config.video_cache.policy == "cache-all"
    assert config.video_cache.max_bytes == 100 * 1024 * 1024


def test_load_app_config_reads_slideshow_and_video_cache_sections(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
mode = "B2"
random = true
video = false
quiet = true

[video_cache]
policy = "bounded-bytes"
max_bytes = 2048
""".strip(),
        encoding="utf-8",
    )

    config = load_app_config(str(config_path))

    assert config.mode == "b2"
    assert config.random is True
    assert config.video is False
    assert config.quiet is True
    assert config.video_cache.policy == "bounded-bytes"
    assert config.video_cache.max_bytes == 2048


def test_load_app_config_rejects_unknown_keys(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
mode = "b1"
unexpected = true
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Unknown slideshow key"):
        load_app_config(str(config_path))


def test_load_app_config_rejects_invalid_mode(tmp_path):
    config_path = tmp_path / "enkan.toml"
    config_path.write_text(
        """
[slideshow]
mode = "not-a-mode"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Invalid slideshow.mode"):
        load_app_config(str(config_path))


def test_merge_config_into_args_preserves_cli_precedence():
    args = Namespace(
        mode="b3",
        random=None,
        dont_recurse=None,
        video=None,
        mute=None,
        quiet=True,
        no_background=None,
    )
    config = AppConfig(
        mode="b1",
        random=True,
        video=False,
        quiet=False,
        no_background=True,
    )

    merged = merge_config_into_args(args, config)

    assert merged.mode == "b3"
    assert merged.random is True
    assert merged.video is False
    assert merged.quiet is True
    assert merged.no_background is True