from collections import deque
from typing import Deque, List, Tuple

try:
    import webrtcvad  # type: ignore
    _HAVE_WEBRTCVAD = True
except Exception:  # pragma: no cover - optional dependency
    webrtcvad = None  # type: ignore
    _HAVE_WEBRTCVAD = False


class WebRTCVADSegmenter:
    """
    WebRTC VAD を用いた音声区間抽出器。

    - 16kHz/mono/16-bit PCM 前提
    - 30ms フレームを基本単位
    - 前後パディング（前: prev_ms, 後: post_ms）
    - 短ポーズ連結（post_ms 内の無音は同発話に含める）
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_ms: int = 30,
        aggressiveness: int = 2,
        prev_ms: int = 200,
        post_ms: int = 300,
        max_utterance_ms: int = 6000,
    ) -> None:
        assert sample_rate == 16000, "WebRTCVADSegmenter expects 16kHz audio"
        assert frame_ms in (10, 20, 30), "frame_ms must be 10/20/30"
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.bytes_per_sample = 2  # PCM16
        self.frame_bytes = int(self.sample_rate * (self.frame_ms / 1000.0)) * self.bytes_per_sample
        self.aggressiveness = aggressiveness
        self.vad = webrtcvad.Vad(aggressiveness) if _HAVE_WEBRTCVAD else None

        # パディング用のフレーム数
        self.prev_frames: int = max(1, prev_ms // self.frame_ms)
        self.post_frames: int = max(1, post_ms // self.frame_ms)

        # バッファ
        self._residual: bytearray = bytearray()
        self._ring: Deque[Tuple[bytes, bool]] = deque(maxlen=self.prev_frames + self.post_frames)
        self._collecting: bool = False
        self._current: List[bytes] = []
        self._post_silence: int = 0
        self._max_frames: int = max_utterance_ms // self.frame_ms

    def feed(self, pcm16_bytes: bytes) -> List[bytes]:
        """
        追加の PCM16 バイト列を投入し、確定した発話（bytes）をリストで返す。
        """
        out: List[bytes] = []
        if not pcm16_bytes:
            return out

        self._residual.extend(pcm16_bytes)

        while len(self._residual) >= self.frame_bytes:
            frame = bytes(self._residual[: self.frame_bytes])
            del self._residual[: self.frame_bytes]

            is_speech = False
            if self.vad is not None:
                try:
                    is_speech = self.vad.is_speech(frame, self.sample_rate)
                except Exception:
                    is_speech = False
            else:
                # 簡易しきい値 VAD（webrtcvad 非導入時のフォールバック）
                import numpy as _np  # local import

                arr = _np.frombuffer(frame, dtype=_np.int16)
                amp = float(_np.mean(_np.abs(arr)))
                # aggressiveness に応じて動的なしきい値を調整
                thr = {0: 150.0, 1: 120.0, 2: 90.0, 3: 70.0}.get(self.aggressiveness, 90.0)
                is_speech = amp >= thr

            self._ring.append((frame, is_speech))

            if is_speech:
                if not self._collecting:
                    # 直近のパディング分（過去フレーム）を先頭に付与
                    past = [f for f, _ in list(self._ring)[-self.prev_frames :]]
                    self._current.extend(past)
                    self._collecting = True
                    self._post_silence = 0
                # 現在フレームを追加
                self._current.append(frame)
                # 長すぎる発話は強制確定
                if len(self._current) >= self._max_frames:
                    out.append(b"".join(self._current))
                    self._reset_collect()
            else:
                if self._collecting:
                    self._post_silence += 1
                    if self._post_silence <= self.post_frames:
                        # 後パディング中
                        self._current.append(frame)
                    else:
                        # 発話確定
                        out.append(b"".join(self._current))
                        self._reset_collect()

        return out

    def _reset_collect(self) -> None:
        self._collecting = False
        self._current = []
        self._post_silence = 0



