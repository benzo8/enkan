import logging
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from typing import Callable

import vlc

from enkan.cache.CachedVideoData import CachedVideoData


@dataclass(frozen=True)
class VideoPlaybackSnapshot:
    active: bool
    paused: bool
    current_time_ms: int | None
    duration_ms: int | None
    seekable: bool
    status_text: str = ""

    @property
    def progress_ratio(self) -> float | None:
        if (
            self.current_time_ms is None
            or self.duration_ms is None
            or self.duration_ms <= 0
        ):
            return None
        return max(0.0, min(self.current_time_ms / self.duration_ms, 1.0))


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

        self._video_frame = None
        self._video_player = None
        self._vlc_instance = None
        self._current_media = None
        self._current_video_payload: CachedVideoData | None = None

        self._pending_video_start_id = None
        self._pending_loop_check_id = None
        self._video_start_request_id = 0
        self._video_cleanup_done = threading.Event()
        self._video_cleanup_done.set()
        self._is_paused = False
        self._status_text = ""

    def _hide_video_frame(self) -> None:
        if self._video_frame is not None:
            self._video_frame.place_forget()

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

    def _cancel_pending_loop_check(self) -> None:
        loop_check_id = self._pending_loop_check_id
        if loop_check_id is None:
            return
        after_cancel = getattr(self.root, "after_cancel", None)
        if callable(after_cancel):
            try:
                after_cancel(loop_check_id)
            except tk.TclError:
                self.logger.debug(
                    "Pending video loop check was already cleared.", exc_info=True
                )
        self._pending_loop_check_id = None

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

    def stop(self, async_cleanup: bool = True, hide: bool = False) -> None:
        self._video_start_request_id += 1
        self._cancel_pending_video_start()
        self._cancel_pending_loop_check()
        if hide:
            self._hide_video_frame()

        video_player = self._video_player
        media = self._current_media
        self._video_player = None
        self._current_media = None
        self._current_video_payload = None
        self._is_paused = False

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
        on_status_changed: Callable[[str], None] | None = None,
    ) -> None:
        self._cancel_pending_video_start()
        self._video_start_request_id += 1
        self._set_status("", on_status_changed)
        request_id = self._video_start_request_id
        self._pending_video_start_id = self.root.after(
            self.debounce_ms,
            lambda: self._start_video_playback(
                request_id,
                image_path,
                media_payload,
                muted,
                on_video_started,
                on_status_changed,
            ),
        )

    def _start_video_playback(
        self,
        request_id: int,
        image_path: str,
        media_payload: CachedVideoData | None,
        muted: bool,
        on_video_started: Callable[[], None] | None = None,
        on_status_changed: Callable[[str], None] | None = None,
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
                    on_status_changed,
                ),
            )
            return

        self._pending_video_start_id = None

        try:
            if self._video_frame is None:
                self._video_frame = tk.Frame(self.root, bg="black")

            self._video_frame.place(
                x=0, y=0, width=self.screen_width, height=self.screen_height
            )
            self._video_frame.update_idletasks()
            self._video_frame.lift()

            if self._vlc_instance is None:
                self._vlc_instance = vlc.Instance("--no-video-title-show", "--quiet")

            media = None
            if isinstance(media_payload, CachedVideoData):
                media = media_payload.to_vlc_media(self._vlc_instance)
            if media is None:
                self.logger.debug("Falling back to path-based VLC media for %s", image_path)
                media = self._vlc_instance.media_new(image_path)
                media.get_mrl()

            self._video_player = self._vlc_instance.media_player_new()
            self._video_player.set_media(media)
            self._video_player.audio_set_mute(muted)
            self._current_media = media
            self._current_video_payload = media_payload
            self._is_paused = False

            window_id = self._video_frame.winfo_id()
            if sys.platform.startswith("win"):
                self._video_player.set_hwnd(window_id)
            elif sys.platform.startswith("linux"):
                self._video_player.set_xwindow(window_id)
            elif sys.platform == "darwin":
                self._video_player.set_nsobject(window_id)
            else:
                raise RuntimeError(f"Unsupported platform: {sys.platform}")

            result = self._video_player.play()
            if result == -1:
                self._set_status("Video playback failed", on_status_changed)
                self.stop(async_cleanup=True, hide=True)
                return
            if callable(on_video_started):
                on_video_started()
            self._set_status("", on_status_changed)
            self._schedule_loop_check(request_id)
        except Exception as exc:
            self.logger.warning("Failed to start video playback: %s", image_path, exc_info=exc)
            self._set_status("Video playback failed", on_status_changed)
            self.stop(async_cleanup=True, hide=True)

    def _schedule_loop_check(self, request_id: int) -> None:
        self._pending_loop_check_id = self.root.after(
            500,
            lambda: self._check_video_ended(request_id),
        )

    def _check_video_ended(self, request_id: int) -> None:
        self._pending_loop_check_id = None
        if request_id != self._video_start_request_id:
            return
        video_player = self._video_player
        if not video_player:
            return
        if self._is_paused:
            self._schedule_loop_check(request_id)
            return

        length = video_player.get_length()
        time = video_player.get_time()

        if length > 0 and time >= length - 200:
            video_player.stop()
            video_player.play()
            self._schedule_loop_check(request_id)
            return

        self._schedule_loop_check(request_id)

    def set_muted(self, muted: bool) -> None:
        if self._video_player is not None:
            self._video_player.audio_set_mute(muted)

    def toggle_pause(self) -> bool:
        if self._video_player is None:
            return False
        self._is_paused = not self._is_paused
        self._video_player.set_pause(1 if self._is_paused else 0)
        return self._is_paused

    def seek_to_ratio(self, ratio: float) -> bool:
        if self._video_player is None:
            return False
        snapshot = self.playback_snapshot()
        if not snapshot.seekable or snapshot.duration_ms is None:
            return False
        clamped = max(0.0, min(float(ratio), 1.0))
        self._video_player.set_time(int(snapshot.duration_ms * clamped))
        return True

    def seek_relative_ms(self, delta_ms: int) -> bool:
        if self._video_player is None:
            return False
        snapshot = self.playback_snapshot()
        if snapshot.current_time_ms is None:
            return False

        target = snapshot.current_time_ms + int(delta_ms)
        if snapshot.duration_ms is not None:
            target = min(target, snapshot.duration_ms)
        target = max(0, target)
        self._video_player.set_time(target)
        return True

    def playback_snapshot(self) -> VideoPlaybackSnapshot:
        video_player = self._video_player
        if video_player is None:
            return VideoPlaybackSnapshot(
                active=False,
                paused=False,
                current_time_ms=None,
                duration_ms=None,
                seekable=False,
                status_text=self._status_text,
            )
        current_time = self._safe_player_int(video_player, "get_time")
        duration = self._safe_player_int(video_player, "get_length")
        seekable = bool(duration and duration > 0)
        return VideoPlaybackSnapshot(
            active=True,
            paused=self._is_paused,
            current_time_ms=current_time if current_time is not None and current_time >= 0 else None,
            duration_ms=duration if duration is not None and duration > 0 else None,
            seekable=seekable,
            status_text=self._status_text,
        )

    def _safe_player_int(self, video_player, method_name: str) -> int | None:
        try:
            return int(getattr(video_player, method_name)())
        except Exception:
            self.logger.debug("Failed to read VLC player %s.", method_name, exc_info=True)
            return None

    def _set_status(
        self,
        status_text: str,
        on_status_changed: Callable[[str], None] | None = None,
    ) -> None:
        self._status_text = status_text
        if callable(on_status_changed):
            on_status_changed(status_text)

    def shutdown(self) -> None:
        self.stop(async_cleanup=False)
        if self._vlc_instance is not None:
            self._vlc_instance.release()
            self._vlc_instance = None
        if self._video_frame is not None:
            self._video_frame.destroy()
            self._video_frame = None
