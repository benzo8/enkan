from __future__ import annotations

import ctypes
import threading
from dataclasses import dataclass

import vlc


@dataclass(frozen=True)
class CachedVideoData:
    path: str
    data: bytes | None = None

    @property
    def is_memory_backed(self) -> bool:
        return self.data is not None

    @property
    def is_path_backed(self) -> bool:
        return self.data is None

    def to_vlc_media(self, vlc_instance: vlc.Instance):
        if self.data is None:
            return vlc_instance.media_new(self.path)
        stream = _InMemoryVideoStream(self.data)
        media = stream.create_media(vlc_instance)
        if media is not None:
            media._enkan_in_memory_stream = stream
        return media


class _InMemoryVideoStream:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._size = len(data)
        self._buffer = ctypes.create_string_buffer(data, self._size)
        self._position = 0
        self._lock = threading.Lock()

        self._opaque_ref = ctypes.py_object(self)
        self._opaque_ptr = ctypes.cast(
            ctypes.pointer(self._opaque_ref), ctypes.c_void_p
        )

        callbacks = vlc.CallbackDecorators
        self._open_cb = callbacks.MediaOpenCb(self._open)
        self._read_cb = callbacks.MediaReadCb(self._read)
        self._seek_cb = callbacks.MediaSeekCb(self._seek)
        self._close_cb = callbacks.MediaCloseCb(self._close)

    def create_media(self, vlc_instance: vlc.Instance):
        return vlc_instance.media_new_callbacks(
            self._open_cb,
            self._read_cb,
            self._seek_cb,
            self._close_cb,
            self._opaque_ptr,
        )

    @staticmethod
    def _from_opaque(opaque) -> "_InMemoryVideoStream":
        return ctypes.cast(
            opaque, ctypes.POINTER(ctypes.py_object)
        ).contents.value

    def _open(self, opaque, datap, sizep) -> int:
        stream = self._from_opaque(opaque)
        with stream._lock:
            stream._position = 0
        datap[0] = opaque
        sizep[0] = stream._size
        return 0

    def _read(self, opaque, buf, length) -> int:
        stream = self._from_opaque(opaque)
        requested = int(length)
        with stream._lock:
            if stream._position >= stream._size:
                return 0

            start = stream._position
            end = min(start + requested, stream._size)
            read_len = end - start
            ctypes.memmove(
                buf,
                ctypes.addressof(stream._buffer) + start,
                read_len,
            )
            stream._position = end
            return read_len

    def _seek(self, opaque, offset) -> int:
        stream = self._from_opaque(opaque)
        target = int(offset)
        if target < 0 or target > stream._size:
            return -1
        with stream._lock:
            stream._position = target
        return 0

    def _close(self, opaque) -> None:
        stream = self._from_opaque(opaque)
        with stream._lock:
            stream._position = 0
