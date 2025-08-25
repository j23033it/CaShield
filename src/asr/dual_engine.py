from concurrent.futures import Future, ThreadPoolExecutor
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

from src.config.asr import ASRConfig


class DualASREngine:
    """
    Two-stage ASR engine using faster-whisper.
    - FAST: low-latency preview (small/int8, beam=2)
    - FINAL: high-accuracy (large-v3/int8, beam=5), executed asynchronously
    """

    def __init__(self, cfg: ASRConfig = ASRConfig) -> None:
        self.cfg = cfg
        self._fast_model: Optional[WhisperModel] = None
        self._final_model: Optional[WhisperModel] = None
        self._executor: Optional[ThreadPoolExecutor] = None

    # ----- lifecycle -----
    def _ensure_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.cfg.FINAL_MAX_WORKERS)
        return self._executor

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None

    # ----- model loading -----
    def _get_fast_model(self) -> WhisperModel:
        if self._fast_model is None:
            self._fast_model = WhisperModel(
                self.cfg.FAST_MODEL,
                device=self.cfg.DEVICE,
                compute_type=self.cfg.FAST_COMPUTE,
            )
        return self._fast_model

    def _get_final_model(self) -> WhisperModel:
        if self._final_model is None:
            self._final_model = WhisperModel(
                self.cfg.FINAL_MODEL,
                device=self.cfg.DEVICE,
                compute_type=self.cfg.FINAL_COMPUTE,
            )
        return self._final_model

    # ----- helpers -----
    @staticmethod
    def _pcm16_to_float32(pcm16: bytes, channels: int = 1) -> np.ndarray:
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        if channels == 2:
            audio = audio.reshape(-1, 2).mean(axis=1)
        return audio

    # ----- ASR -----
    def transcribe_fast(self, pcm16_bytes: bytes, channels: int = 1) -> str:
        audio = self._pcm16_to_float32(pcm16_bytes, channels=channels)
        segments, _ = self._get_fast_model().transcribe(
            audio,
            language=self.cfg.LANGUAGE,
            beam_size=self.cfg.FAST_BEAM,
            temperature=self.cfg.TEMPERATURE,
            condition_on_previous_text=False,
            vad_filter=self.cfg.VAD_FILTER,
            initial_prompt=None,
            log_prob_threshold=self.cfg.LOG_PROB_THRESHOLD,
            no_speech_threshold=self.cfg.NO_SPEECH_THRESHOLD,
        )
        return "".join(seg.text for seg in segments).strip()

    def submit_final(self, pcm16_bytes: bytes, channels: int = 1) -> Future[str]:
        audio = self._pcm16_to_float32(pcm16_bytes, channels=channels)
        executor = self._ensure_executor()

        def _run(a: np.ndarray) -> str:
            segments, _ = self._get_final_model().transcribe(
                a,
                language=self.cfg.LANGUAGE,
                beam_size=self.cfg.FINAL_BEAM,
                temperature=self.cfg.TEMPERATURE,
                condition_on_previous_text=False,
                vad_filter=self.cfg.VAD_FILTER,
                initial_prompt=None,
                log_prob_threshold=self.cfg.LOG_PROB_THRESHOLD,
                no_speech_threshold=self.cfg.NO_SPEECH_THRESHOLD,
            )
            return "".join(seg.text for seg in segments).strip()

        return executor.submit(_run, audio)

