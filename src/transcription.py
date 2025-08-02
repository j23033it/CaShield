

from faster_whisper import WhisperModel
import numpy as np
import src.config as cfg                     # ← cfg を先に読み込む
from src.models import TranscriptionResult, AudioData

class TranscriptionEngine:
    def __init__(self, language: str = "ja"):
        self.model_name = cfg.WHISPER_MODEL
        self.language = language
        self._model = None
    
    def load_model(self):
        """
        Whisperモデルを読み込む
        """
        try:
            # faster-whisper でモデルをロード
            self._model = WhisperModel(
                cfg.WHISPER_MODEL,
                device       = cfg.DEVICE,
                compute_type = cfg.COMPUTE_TYPE
            )
            print(f"Whisperモデル '{cfg.WHISPER_MODEL}' を読み込みました")
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
        """
        bytes -> numpy(float32) へ変換し、faster-whisper で文字起こし
        """
        try:
            # 16-bit PCM → float32 [-1, 1]
            audio = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0

            # ステレオの場合はモノラル平均
            if channels == 2:
                audio = audio.reshape(-1, 2).mean(axis=1)

            segments, info = self._model.transcribe(
                audio,
                language    = cfg.LANGUAGE,
                beam_size   = cfg.BEAM_SIZE,
                temperature = cfg.TEMPERATURE,
                vad_filter  = True
            )

            text = "".join(seg.text for seg in segments)

            # confidence ≒ exp(mean(avg_logprob))
            logprobs = [seg.avg_logprob for seg in segments if seg.avg_logprob is not None]
            confidence = float(np.exp(np.mean(logprobs))) if logprobs else None

            return TranscriptionResult(
                text=text,
                confidence=confidence,
                segments=list(segments),
                metadata={"model": cfg.WHISPER_MODEL, "duration": info.duration},
                success=True
            )

        except Exception as e:
            return TranscriptionResult(
                text="",
                success=False,
                error_message=f"音声処理エラー: {e}"
            )
