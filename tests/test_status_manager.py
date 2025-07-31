# tests/test_status_manager.py

import pytest
import threading
from src.status_manager import StatusManager, Status

def test_initial_status():
    sm = StatusManager()
    assert sm.get_status() == Status.IDLE

def test_set_get_status():
    sm = StatusManager()
    sm.set_status(Status.RECORDING)
    assert sm.get_status() == Status.RECORDING
    sm.set_status(Status.TRANSCRIBING)
    assert sm.get_status() == Status.TRANSCRIBING

def test_is_recording_flag():
    sm = StatusManager()
    assert not sm.is_recording()
    sm.set_status(Status.RECORDING)
    assert sm.is_recording()

def test_thread_safety():
    sm = StatusManager()

    def worker(status_to_set):
        for _ in range(1000):
            sm.set_status(status_to_set)
            assert sm.get_status() in Status

    threads = []
    for st in [Status.RECORDING, Status.TRANSCRIBING, Status.IDLE]:
        t = threading.Thread(target=worker, args=(st,))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    # 最後に設定したステータスが取得できる
    assert sm.get_status() in {Status.IDLE, Status.RECORDING, Status.TRANSCRIBING}
