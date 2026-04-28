import logging
import sys
import threading
import tkinter as tk
from typing import Callable

import vlc

from enkan.cache.CachedVideoData import CachedVideoData


class VideoPlaybackController:
    """Owns VLC video playback lifecycle for the slideshow UI."""

    def __init__(
        self,
        root: tk.Misc,
        screen_width: int,
        screen_height: int,
        logger: logging.Logger,
        debounce_ms: int = 150,
    ) -> None:
        self.root = root
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.logger = logger
        self.debounce_ms = debounce_ms

        self.video_frame = None
        self.video_player = None
        self.vlc_instance = None
        self.current_vlc_media = None
        self.current_video_payload: CachedVideoData | None = None

        self._pending_video_start_id = None
        self._video_start_request_id = 0
        self._video_cleanup_done = threading.Event()
        self._video_cleanup_done.set()

    def hide_video_frame(self) -> None:
        if self.video_frame is not None:
            self.video_frame.place_forget()

    def _cancel_pending_video_start(self) -> None:
        pending_start_id = self._pending_video_start_id
        if pending_start_id is None:
            return
        after_cancel = getattr(self.root, "after_cancel", None)
        if callable(after_cancel):
            try:
                after_cancel(pending_start_id)
            except tk.TclError:
                self.logger.debug(
                    "Pending video start was already cleared.", exc_info=True
                )
        self._pending_video_start_id = None

    def _is_video_cleanup_active(self) -> bool:
        return not self._video_cleanup_done.is_set()

    def _dispose_vlc_resources(self, video_player, media) -> None:
        try:
            if video_player is not None:
                try:
                    video_player.stop()
                except Exception:
                    self.logger.debug(
                        "Failed to stop VLC player cleanly.", exc_info=True
                    )
                try:
                    video_player.release()
                except Exception:
                    self.logger.debug(
                        "Failed to release VLC player cleanly.", exc_info=True
                    )
            if media is not None:
                try:
                    media.release()
                except Exception:
                    self.logger.debug(
                        "Failed to release VLC media cleanly.", exc_info=True
                    )
        finally:
            self._video_cleanup_done.set()

    def release_resources(self, async_cleanup: bool = True) -> None:
        self._cancel_pending_video_start()

        video_player = self.video_player
        media = self.current_vlc_media
        self.video_player = None
        self.current_vlc_media = None
        self.current_video_payload = None

        if video_player is None and media is None:
            return

        self._video_cleanup_done.clear()
        if async_cleanup:
            threading.Thread(
                target=self._dispose_vlc_resources,
                args=(video_player, media),
                daemon=True,
            ).start()
            return

        self._dispose_vlc_resources(video_player, media)

    def schedule_start(
        self,
        image_path: str,
        media_payload: CachedVideoData | None,
        muted: bool,
        on_video_started: Callable[[], None] | None = None,
    ) -> None:
        self._video_start_request_id += 1
        request_id = self._video_start_request_id
        self._pending_video_start_id = self.root.after(
            self.debounce_ms,
            lambda: self._start_video_playback(
                request_id,
                image_path,
                media_payload,
                muted,
                on_video_started,
            ),
        )

    def _start_video_playback(
        self,
        request_id: int,
        image_path: str,
        media_payload: CachedVideoData | None,
        muted: bool,
        on_video_started: Callable[[], None] | None = None,
    ) -> None:
        if request_id != self._video_start_request_id:
            return
        if self._is_video_cleanup_active():
            self._pending_video_start_id = self.root.after(
                30,
                lambda: self._start_video_playback(
                    request_id,
                    image_path,
                    media_payload,
                    muted,
                    on_video_started,
                ),
            )
            return

        self._pending_video_start_id = None

        if self.video_frame is None:
            self.video_frame = tk.Frame(self.root, bg="black")

        self.video_frame.place(x=0, y=0, width=self.screen_width, height=self.screen_height)
        self.video_frame.update_idletasks()
        self.video_frame.lift()

        if self.vlc_instance is None:
            self.vlc_instance = vlc.Instance("--no-video-title-show", "--quiet")

        media = None
        if isinstance(media_payload, CachedVideoData):
            media = media_payload.to_vlc_media(self.vlc_instance)
        if media is None:
            self.logger.debug("Falling back to path-based VLC media for %s", image_path)
            media = self.vlc_instance.media_new(image_path)
            media.get_mrl()

        self.video_player = self.vlc_instance.media_player_new()
        self.video_player.set_media(media)
        self.video_player.audio_set_mute(muted)
        self.current_vlc_media = media
        self.current_video_payload = media_payload

        window_id = self.video_frame.winfo_id()
        if sys.platform.startswith("win"):
            self.video_player.set_hwnd(window_id)
        elif sys.platform.startswith("linux"):
            self.video_player.set_xwindow(window_id)
        elif sys.platform == "darwin":
            self.video_player.set_nsobject(window_id)
        else:
            raise RuntimeError(f"Unsupported platform: {sys.platform}")

        self.video_player.play()
        if callable(on_video_started):
            on_video_started()

    def toggle_mute(self, fallback_mute: bool) -> bool:
        if self.video_player is None:
            return fallback_mute
        current_mute = bool(self.video_player.audio_get_mute())
        new_mute = not current_mute
        self.video_player.audio_set_mute(new_mute)
        return new_mute

    def shutdown(self) -> None:
        self.release_resources(async_cleanup=False)
        if self.vlc_instance is not None:
            self.vlc_instance.release()
            self.vlc_instance = None
        if self.video_frame is not None:
            self.video_frame.destroy()
            self.video_frame = None
