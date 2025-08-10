from collections import deque
from typing import Deque, Optional

import numpy as np
import sounddevice as sd


class SDInput:
    """
    sounddevice RawInputStream + リングバッファ（16kHz/mono/PCM16）
    """

    def __init__(self, sample_rate: int = 16000, block_ms: int = 20, max_ms: int = 5000) -> None:
        self.sample_rate = sample_rate
        self.block_ms = block_ms
        self.block_samples = int(self.sample_rate * (self.block_ms / 1000.0))
        self.bytes_per_sample = 2
        self.channels = 1
        self.dtype = "int16"
        self.max_blocks = max(1, max_ms // self.block_ms)
        self._buf: Deque[bytes] = deque(maxlen=self.max_blocks)
        self._stream: Optional[sd.RawInputStream] = None

    def start(self, device: Optional[int] = None) -> None:
        def callback(indata, frames, time_info, status):  # noqa: D401
            if status:
                # drop if overflow
                pass
            self._buf.append(bytes(indata))

        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            blocksize=self.block_samples,
            callback=callback,
            device=device,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
        self._stream = None

    def read_bytes(self) -> bytes:
        return b"".join(self._buf)

    def pop_all(self) -> bytes:
        if not self._buf:
            return b""
        chunks = list(self._buf)
        self._buf.clear()
        return b"".join(chunks)



