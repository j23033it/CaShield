# src/models.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any

@dataclass
class AudioData:
    """
    録音した音声データとそのメタ情報を保持するモデル
    """
    raw_bytes: bytes
    sample_rate: int
    channels: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def duration_seconds(self) -> float:
        """
        音声データの長さ（秒）を計算して返す。
        """
        # raw_bytes は PCM 16bit リニア等を想定。この計算はサンプル数 / サンプリングレート
        bytes_per_sample = 2  # PCM16 は 2 バイト／サンプル
        total_samples = len(self.raw_bytes) // (bytes_per_sample * self.channels)
        return total_samples / self.sample_rate


@dataclass
class TranscriptionResult:
    """
    Whisper 等の音声認識エンジンの返す文字起こし結果とスコア等を保持するモデル
    """
    text: str
    confidence: Optional[float] = None
    segments: Optional[Any] = None  # 将来、細かいセグメント情報を保持する場合用
    metadata: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error_message: Optional[str] = None


@dataclass
class AppConfig:
    """
    アプリ全体の設定を保持するモデル
    （例: Whisperモデル名、言語設定 など）
    """
    whisper_model: str = "base"
    language: str = "ja"
    extra_params: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        """
        dict形式で設定を取得
        """
        return {
            "whisper_model": self.whisper_model,
            "language": self.language,
            **self.extra_params
        }
