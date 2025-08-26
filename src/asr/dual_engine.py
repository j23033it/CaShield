"""
src.asr.dual_engine

faster-whisper を用いた二段（FAST/FINAL）ASR エンジン実装。

- FAST: 低レイテンシのプレビュー用。軽量モデル（small など）＋低ビームで即時性を重視。
- FINAL: 高精度の確定結果。重量モデル（large-v3 など）＋高ビームで精度を重視し、非同期実行。

用途:
- scripts/rt_stream.py から、1 発話の FAST 結果を即時ログに追記し、FINAL は完了後に同一ID行を置換。
"""

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

from src.config.asr import ASRConfig


class DualASREngine:
    """
    二段ASRエンジンの窓口クラス。

    - モデルのロードは遅延（初回呼び出し時）に行い、以降は再利用。
    - FINAL はスレッドプールで非同期実行し、UI/録音スレッドをブロックしない。
    """

    def __init__(self, cfg: ASRConfig = ASRConfig) -> None:
        """設定オブジェクトを受け取り、内部状態を初期化する。"""
        self.cfg = cfg
        self._fast_model: Optional[WhisperModel] = None
        self._final_model: Optional[WhisperModel] = None
        self._executor: Optional[ThreadPoolExecutor] = None

    # ----- lifecycle -----
    def _ensure_executor(self) -> ThreadPoolExecutor:
        """FINAL 用のスレッドプールを（なければ）生成して返す。"""
        if self._executor is None:
            # 並列度は ASRConfig.FINAL_MAX_WORKERS で制御（コード内設定）
            self._executor = ThreadPoolExecutor(max_workers=self.cfg.FINAL_MAX_WORKERS)
        return self._executor

    def close(self) -> None:
        """スレッドプールを停止してリソースを解放する。"""
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None

    # ----- model loading -----
    def _get_fast_model(self) -> WhisperModel:
        """FAST 用モデルを遅延ロードして返す。"""
        if self._fast_model is None:
            self._fast_model = WhisperModel(
                self.cfg.FAST_MODEL,
                device=self.cfg.DEVICE,
                compute_type=self.cfg.FAST_COMPUTE,
            )
        return self._fast_model

    def _get_final_model(self) -> WhisperModel:
        """FINAL 用モデルを遅延ロードして返す。"""
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
        """PCM16 (bytes) → float32 [-1, 1] に正規化し、ステレオはモノラル平均する。"""
        # 16bit PCM を float32 にスケーリング（32768 = 2^15）
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        # ステレオ入力の場合はLRの平均を取りモノラル化
        if channels == 2:
            audio = audio.reshape(-1, 2).mean(axis=1)
        return audio

    # ----- ASR -----
    def transcribe_fast(self, pcm16_bytes: bytes, channels: int = 1) -> str:
        """FAST（低レイテンシ）用の認識を同期実行してテキストを返す。"""
        # 前処理：PCM16 → float32
        audio = self._pcm16_to_float32(pcm16_bytes, channels=channels)
        # 軽量モデルで即時性重視の推論パラメータを指定
        segments, _ = self._get_fast_model().transcribe(
            audio,
            language=self.cfg.LANGUAGE,                 # 日本語固定
            beam_size=self.cfg.FAST_BEAM,              # 低ビームで高速化
            temperature=self.cfg.TEMPERATURE,
            condition_on_previous_text=False,          # 文脈引き継ぎはしない（遅延回避）
            vad_filter=self.cfg.VAD_FILTER,            # 入力はVAD済みだが保険で有効
            initial_prompt=None,                       # 必要なら ASRConfig で付与可
            log_prob_threshold=self.cfg.LOG_PROB_THRESHOLD,
            no_speech_threshold=self.cfg.NO_SPEECH_THRESHOLD,
        )
        return "".join(seg.text for seg in segments).strip()

    def submit_final(self, pcm16_bytes: bytes, channels: int = 1) -> Future[str]:
        """FINAL（高精度）認識を非同期で実行し、結果文字列の Future を返す。"""
        # 前処理：PCM16 → float32
        audio = self._pcm16_to_float32(pcm16_bytes, channels=channels)
        executor = self._ensure_executor()

        def _run(a: np.ndarray) -> str:
            # 高精度モデルでビーム幅を広げ、最終結果を取得
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

        # スレッドプールでバックグラウンド実行
        return executor.submit(_run, audio)
