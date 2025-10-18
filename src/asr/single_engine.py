"""
src.asr.single_engine

faster-whisper を用いた単一段 ASR エンジン。

- 即時性と精度を単一モデルで両立するため、ビーム幅や温度などの推論パラメータは
  `src/config/asr.py` のコード内設定から参照します。
- PCM16 の生データを float32 に正規化し、WhisperModel へ入力して文字起こしを行います。
"""

from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

from src.config.asr import ASRConfig


class SingleASREngine:
    """単一段 ASR エンジン。

    責務:
    - コード内設定 `ASRConfig` を参照して WhisperModel を遅延ロードする。
    - 音声バイト列（PCM16, mono/stereo）を float32 波形へ変換して推論する。
    - 文字起こし結果のテキストを同期的に返す。

    主な属性:
    - cfg: `ASRConfig` の参照。モデル名・ビーム幅などの集中設定。
    - _model: WhisperModel のキャッシュ。初回推論時にロードし再利用。
    """

    def __init__(self, cfg: ASRConfig = ASRConfig) -> None:
        """設定オブジェクトを保持し、モデルキャッシュを初期化する。"""

        self.cfg = cfg
        self._model: Optional[WhisperModel] = None

    # ----- model lifecycle -----
    def _ensure_model(self) -> WhisperModel:
        """WhisperModel を遅延ロードして返す。"""

        if self._model is None:
            # WhisperModel は重い初期化を伴うため、単一インスタンスをキャッシュして再利用
            self._model = WhisperModel(
                self.cfg.MODEL_NAME,
                device=self.cfg.DEVICE,
                compute_type=self.cfg.COMPUTE_TYPE,
            )
        return self._model

    def close(self) -> None:
        """モデル参照を破棄してメモリ解放を促す。"""

        # CTranslate2 の WhisperModel はガベージコレクションで解放されるため参照を消すのみ
        self._model = None

    # ----- helpers -----
    @staticmethod
    def _pcm16_to_float32(pcm16: bytes, channels: int = 1) -> np.ndarray:
        """PCM16 を float32 [-1, 1] に正規化し、必要に応じてモノラル化する。"""

        # 16bit PCM を float32 にスケーリング（32768 = 2^15）
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        if channels == 2:
            # ステレオ入力の場合は左右チャンネルの平均を取りモノラル化
            audio = audio.reshape(-1, 2).mean(axis=1)
        return audio

    # ----- ASR -----
    def transcribe(self, pcm16_bytes: bytes, channels: int = 1) -> str:
        """単一段の文字起こしを実行し結果文字列を返す。"""

        # 前処理：PCM16 → float32
        audio = self._pcm16_to_float32(pcm16_bytes, channels=channels)

        # WhisperModel で推論（ビーム幅などは ASRConfig のコード内設定を使用）
        segments, _ = self._ensure_model().transcribe(
            audio,
            language=self.cfg.LANGUAGE,                # 日本語固定運用
            beam_size=self.cfg.BEAM_SIZE,              # 単一段でも精度確保のためのビーム幅
            temperature=self.cfg.TEMPERATURE,
            condition_on_previous_text=False,          # 遅延を抑えるため前文脈は使用しない
            vad_filter=self.cfg.VAD_FILTER,
            initial_prompt=None,                       # 必要なら ASRConfig で指定
            log_prob_threshold=self.cfg.LOG_PROB_THRESHOLD,
            no_speech_threshold=self.cfg.NO_SPEECH_THRESHOLD,
        )
        return "".join(seg.text for seg in segments).strip()

