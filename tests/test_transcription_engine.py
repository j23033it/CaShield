# tests/test_transcription_engine.py

import pytest
from src.transcription import TranscriptionEngine
from src.models import TranscriptionResult

class DummyModel:
    def transcribe(self, audio, language):
        return {"text": "テスト", "segments": [{"avg_logprob": -0.2}]}

@pytest.fixture(autouse=True)
def patch_whisper(monkeypatch):
    from faster_whisper import WhisperModel
    monkeypatch.setattr(WhisperModel, "load_model", lambda name: DummyModel())

def test_transcribe_basic():
    engine = TranscriptionEngine(model_name="dummy", language="ja")
    raw = b"\x00\x00" * 16000  # 1秒分の無音
    result = engine.transcribe(raw, sample_rate=16000, channels=1)
    assert isinstance(result, TranscriptionResult)
    assert result.text == "テスト"
    assert 0.0 < result.confidence <= 1.0
