# tests/test_models.py

import pytest
from datetime import datetime, timedelta

from src.models import AudioData, TranscriptionResult, AppConfig

def test_audio_data_duration():
    # 1秒分のサンプルをモック（サンプルレート16kHz、モノラル、PCM16）
    sample_rate = 16000
    channels = 1
    # 1秒 -> 16000 samples * 2 bytes
    raw = b"\x00\x00" * sample_rate * channels
    audio = AudioData(raw_bytes=raw, sample_rate=sample_rate, channels=channels)
    assert abs(audio.duration_seconds() - 1.0) < 1e-6

def test_transcription_result_defaults():
    tr = TranscriptionResult(text="こんにちは")
    assert tr.text == "こんにちは"
    assert tr.confidence is None
    assert isinstance(tr.metadata, dict)

def test_app_config_as_dict():
    cfg = AppConfig(whisper_model="small", language="en")
    d = cfg.as_dict()
    assert d["whisper_model"] == "small"
    assert d["language"] == "en"
