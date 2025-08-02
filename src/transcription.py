# src/transcription.py

from faster_whisper import WhisperModel
import numpy as np
from src.models import TranscriptionResult, AudioData

class TranscriptionEngine:
    def __init__(self, model_name: str = "tiny", language: str = "ja"):
        self.model_name = model_name
        self.language = language
        self._model = None
    
    def load_model(self):
        """
        Whisperモデルを読み込む
        """
        try:
            self._model = WhisperModel(
                cfg.WHISPER_MODEL,
                device       = cfg.DEVICE,
                compute_type = cfg.COMPUTE_TYPE
            )
            print(f"Whisperモデル '{self.model_name}' を読み込みました")
        except Exception as e:
            raise RuntimeError(f"Whisperモデルの読み込みに失敗: {e}")
    
    def transcribe_audio(self, audio_data: AudioData) -> TranscriptionResult:
        """
        AudioDataを受け取って文字起こしを実行
        """
        if self._model is None:
            return TranscriptionResult(
                text="",
                success=False,
                error_message="モデルが読み込まれていません。load_model()を先に実行してください"
            )
        
        try:
            return self.transcribe(audio_data.raw_bytes, audio_data.sample_rate, audio_data.channels)
        except Exception as e:
            return TranscriptionResult(
                text="",
                success=False,
                error_message=f"文字起こしエラー: {e}"
            )

    def transcribe(self, raw_bytes: bytes, sample_rate: int, channels: int) -> TranscriptionResult:
        # raw_bytes -> numpy array（float32, [-1,1]）に変換
        try:
            audio = (
                np.frombuffer(raw_bytes, dtype=np.int16)
                .astype(np.float32) / 32768.0
            )
            # Whisper に入力
            result = self._model.transcribe(audio, language=self.language)
            text = result.get("text", "")
            segments = result.get("segments", [])
            # 簡易的な confidence 計算
            confidence = None
            if segments:
                logprobs = [seg.get("avg_logprob", 0.0) for seg in segments]
                confidence = float(np.exp(np.mean(logprobs)))
            return TranscriptionResult(
                text=text,
                confidence=confidence,
                segments=segments,
                metadata=result,
                success=True
            )
        except Exception as e:
            return TranscriptionResult(
                text="",
                success=False,
                error_message=f"音声処理エラー: {e}"
            )
