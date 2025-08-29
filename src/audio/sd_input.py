from collections import deque
from typing import Deque, Optional, Union

import threading
import time
import sounddevice as sd


class SDInput:
    """
    sounddevice RawInputStream + リングバッファ（16kHz/mono/PCM16）。

    - 目的: 低レイテンシ音声の取り込み。
    - 特徴: デバイス名（部分一致）指定に対応し、コールバックの最終呼出時刻を保持して
            ホットプラグ検知（無音/停止検知）を支援する。
    """

    def __init__(self, sample_rate: int = 16000, block_ms: int = 20, max_ms: int = 5000) -> None:
        # 基本パラメータ
        self.sample_rate = sample_rate
        self.block_ms = block_ms
        self.block_samples = int(self.sample_rate * (self.block_ms / 1000.0))
        self.bytes_per_sample = 2
        self.channels = 1
        self.dtype = "int16"

        # バッファと状態
        self.max_blocks = max(1, max_ms // self.block_ms)
        self._buf: Deque[bytes] = deque(maxlen=self.max_blocks)
        self._lock = threading.Lock()
        self._stream: Optional[sd.RawInputStream] = None
        self._last_cb_ts = 0.0  # 最終コールバック時刻（monotonic 秒）
        self._last_bytes = 0    # 直近のバイト数（デバッグ用）

    def _resolve_device(self, device: Optional[Union[int, str]]) -> Optional[Union[int, None]]:
        """
        デバイス指定を sounddevice 用に解決。
        - None: デフォルトに委譲
        - int: そのまま返却
        - str: `sd.query_devices()` から name 部分一致（大文字小文字無視）でインデックスを選ぶ
               入力チャンネルが 1 以上のデバイスのみ対象
        """
        if device is None or isinstance(device, int):
            return device

        # 文字列の場合は部分一致検索
        want = device.lower()
        try:
            devs = sd.query_devices()
        except Exception:
            return None

        # 入力デバイスのみ対象
        candidates = [i for i, d in enumerate(devs) if d.get("max_input_channels", 0) > 0]
        for idx in candidates:
            name = str(devs[idx].get("name", "")).lower()
            if want in name:
                return idx
        return None

    def start(self, device: Optional[Union[int, str]] = None) -> None:
        """音声入力ストリームを開始。

        - `device`: None / 入力デバイス index / デバイス名（部分一致）
        - コールバック内で例外は握り、ストリーム停止を促すため CallbackStop を発行
        """

        def callback(indata, frames, time_info, status):  # noqa: D401
            try:
                # ポーリング用マーカーを更新
                self._last_cb_ts = time.monotonic()
                if status:
                    # 入出力の under/overflow などはログは出さず捨てる
                    pass
                # バイナリへ詰める
                with self._lock:
                    b = bytes(indata)
                    self._last_bytes = len(b)
                    self._buf.append(b)
            except Exception:
                # コールバック内の例外はプロセスを落とさないため停止指示のみ
                raise sd.CallbackStop

        # デバイス解決（部分一致対応）
        dev_idx = self._resolve_device(device)

        # 既存ストリームがあれば停止してから作り直す
        self.stop()

        self._last_cb_ts = 0.0
        self._last_bytes = 0

        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            blocksize=self.block_samples,
            callback=callback,
            device=dev_idx,
        )
        self._stream.start()

    def stop(self) -> None:
        """入力ストリームを停止・解放（例外は握る）。"""
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
        self._stream = None

    def read_bytes(self) -> bytes:
        """バッファ内の内容を結合して返す（破壊しない）。"""
        with self._lock:
            return b"".join(self._buf)

    def pop_all(self) -> bytes:
        """バッファをすべて取り出してクリアする。"""
        with self._lock:
            if not self._buf:
                return b""
            chunks = list(self._buf)
            self._buf.clear()
            return b"".join(chunks)

    # ---- liveness / 監視系ユーティリティ ----
    def time_since_last_callback(self) -> float:
        """最終コールバックからの経過秒（コールバック未実行なら+inf）。"""
        if self._last_cb_ts <= 0:
            return float("inf")
        return max(0.0, time.monotonic() - self._last_cb_ts)

    def is_active(self) -> bool:
        """ストリームが存在し active かどうか。"""
        return bool(self._stream is not None and getattr(self._stream, "active", False))
