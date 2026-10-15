"""Tiny ctypes binding for libopus (encoder + decoder). macOS: `brew install opus`."""
from __future__ import annotations

import ctypes
import ctypes.util
import os

_CANDIDATES = [
    os.getenv("OPUS_LIB", ""),
    ctypes.util.find_library("opus") or "",
    "/opt/homebrew/lib/libopus.dylib",
    "/usr/local/lib/libopus.dylib",
    "libopus.so.0",
    "libopus.so",
]

_lib = None
for _c in _CANDIDATES:
    if not _c:
        continue
    try:
        _lib = ctypes.CDLL(_c)
        break
    except OSError:
        continue
if _lib is None:
    raise ImportError("libopus not found. macOS: `brew install opus`; Debian: `apt install libopus0`")

OPUS_APPLICATION_VOIP = 2048
OPUS_SET_BITRATE_REQUEST = 4002

_lib.opus_encoder_create.restype = ctypes.c_void_p
_lib.opus_encoder_create.argtypes = [ctypes.c_int32, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
_lib.opus_encode.restype = ctypes.c_int32
_lib.opus_encode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int16), ctypes.c_int, ctypes.c_char_p, ctypes.c_int32]
_lib.opus_encoder_destroy.argtypes = [ctypes.c_void_p]
_lib.opus_decoder_create.restype = ctypes.c_void_p
_lib.opus_decoder_create.argtypes = [ctypes.c_int32, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
_lib.opus_decode.restype = ctypes.c_int
_lib.opus_decode.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int32, ctypes.POINTER(ctypes.c_int16), ctypes.c_int, ctypes.c_int]
_lib.opus_decoder_destroy.argtypes = [ctypes.c_void_p]
_lib.opus_encoder_ctl.restype = ctypes.c_int
_lib.opus_encoder_ctl.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int32]


class OpusError(RuntimeError):
    pass


class Encoder:
    def __init__(self, rate: int, channels: int = 1, bitrate: int = 32000) -> None:
        err = ctypes.c_int()
        self._st = _lib.opus_encoder_create(rate, channels, OPUS_APPLICATION_VOIP, ctypes.byref(err))
        if err.value != 0 or not self._st:
            raise OpusError(f"opus_encoder_create failed: {err.value}")
        _lib.opus_encoder_ctl(self._st, OPUS_SET_BITRATE_REQUEST, bitrate)
        self.rate, self.channels = rate, channels
        self._out = ctypes.create_string_buffer(4000)

    def encode(self, pcm: bytes) -> bytes:
        n = len(pcm) // 2 // self.channels
        buf = (ctypes.c_int16 * (n * self.channels)).from_buffer_copy(pcm)
        r = _lib.opus_encode(self._st, buf, n, self._out, len(self._out))
        if r < 0:
            raise OpusError(f"opus_encode failed: {r}")
        return self._out.raw[:r]

    def __del__(self) -> None:
        if getattr(self, "_st", None):
            _lib.opus_encoder_destroy(self._st)
            self._st = None


class Decoder:
    def __init__(self, rate: int, channels: int = 1) -> None:
        err = ctypes.c_int()
        self._st = _lib.opus_decoder_create(rate, channels, ctypes.byref(err))
        if err.value != 0 or not self._st:
            raise OpusError(f"opus_decoder_create failed: {err.value}")
        self.rate, self.channels = rate, channels
        self._max = rate * 120 // 1000  # 120 ms max frame
        self._pcm = (ctypes.c_int16 * (self._max * channels))()

    def decode(self, packet: bytes) -> bytes:
        r = _lib.opus_decode(self._st, packet, len(packet), self._pcm, self._max, 0)
        if r < 0:
            raise OpusError(f"opus_decode failed: {r}")
        return ctypes.string_at(self._pcm, r * 2 * self.channels)

    def __del__(self) -> None:
        if getattr(self, "_st", None):
            _lib.opus_decoder_destroy(self._st)
            self._st = None
