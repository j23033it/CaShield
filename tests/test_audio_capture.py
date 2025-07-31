# tests/test_audio_capture.py
import pytest
import time
from src.audio_capture import AudioCapture

class DummyStream:
    def __init__(self, frames): self.frames = frames
    def read(self, chunk, exception_on_overflow): return self.frames.pop(0)
    def stop_stream(self): pass
    def close(self): pass

class DummyPyAudio:
    paInt16 = 8
    def __init__(self): pass
    def open(self, format, channels, rate, input, frames_per_buffer):
        # 5チャンク分のデータを返す
        data = [b'\x00\x01' * frames_per_buffer] * 5
        return DummyStream(data)
    def terminate(self): pass

@pytest.fixture(autouse=True)
def patch_pyaudio(monkeypatch):
    monkeypatch.setattr('pyaudio.PyAudio', DummyPyAudio)

def test_start_stop_and_get_data():
    ac = AudioCapture(sample_rate=16000, channels=1, chunk_size=1024)
    ac.start_capture()
    time.sleep(0.1)
    ac.stop_capture()
    raw = ac.get_audio_data()
    assert isinstance(raw, bytes) and len(raw) > 0

def test_validate_short_audio():
    ac = AudioCapture()
    ac._frames = [b'\x00\x00'] * 10  # とても短い録音
    with pytest.raises(ValueError):
        ac.validate(min_duration_sec=0.1)
