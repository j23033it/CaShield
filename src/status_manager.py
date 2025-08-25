# src/status_manager.py

from enum import Enum, auto
import threading

class Status(Enum):
    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    ERROR = auto()

class StatusManager:
    """
    アプリケーションの現在状態を管理するクラス。
    スレッドセーフに状態設定／取得が可能。
    """
    def __init__(self):
        self._status = Status.IDLE
        self._lock = threading.Lock()

    def set_status(self, status: Status):
        """
        ステータスを更新する。
        """
        with self._lock:
            self._status = status

    def get_status(self) -> Status:
        """
        現在のステータスを返す。
        """
        with self._lock:
            return self._status

    def is_recording(self) -> bool:
        """
        現在が RECORDING 状態かどうかを返す。
        """
        return self.get_status() == Status.RECORDING
