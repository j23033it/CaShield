from typing import Dict, Generator, Iterable

import numpy as np
from faster_whisper import WhisperModel


class FasterWhisperEngine:
    """
    faster-whisper のストリーミング互換ラッパ。

    transcribe_stream(frames_iter) -> generator of {type: partial/final, text, ts}
    - frames_iter: PCM16 bytes iterable (e.g., VADで切り出したチャンク)
    - ストリーム単位で model.transcribe(audio) を呼ぶ簡易版
    """

    def __init__(
        self,
        model_name: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "ja",
        beam_size: int = 3,
        condition_on_previous_text: bool = False,
        vad_filter: bool = True,
        initial_prompt: str = "",
    ) -> None:
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
        self.params = dict(
            language=language,
            beam_size=beam_size,
            condition_on_previous_text=condition_on_previous_text,
            vad_filter=vad_filter,
            initial_prompt=initial_prompt or None,
        )

    def _pcm16_to_float32(self, pcm16: bytes, channels: int = 1) -> np.ndarray:
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        if channels == 2:
            audio = audio.reshape(-1, 2).mean(axis=1)
        return audio

    def transcribe_stream(self, frames: Iterable[bytes], channels: int = 1) -> Generator[Dict, None, None]:
        for chunk in frames:
            if not chunk:
                continue
            audio = self._pcm16_to_float32(chunk, channels=channels)
            segments, _ = self.model.transcribe(audio, **self.params)
            text = "".join(seg.text for seg in segments)
            yield {"type": "final", "text": text}



