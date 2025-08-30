"""
音声入力モジュール（sounddevice ラッパー）

概要:
- PortAudio バックエンドの `sounddevice.RawInputStream` を用いて、16kHz/モノラル/PCM16 の音声を
  低レイテンシ（既定 20ms ブロック）で取り込み、リングバッファ（deque）へ蓄積・取り出しする
  ユーティリティクラス `SDInput` を提供する。

入出力/主要責務:
- 入力: OS のデフォルトまたは指定デバイス（index または名称部分一致）からのPCM16生バイト。
- 出力: `read_bytes()` / `pop_all()` によりバッファへ蓄積されたバイト列。
- 監視: 最終コールバック時刻やストリームの生存状況を公開し、ホットプラグ検知・自動再起動の実装を支援。

設計方針:
- .env は使用せず、パラメータはコード内設定から受け取る前提。
- I/O スレッドの例外は握り、停止指示（CallbackStop）で上位へ復帰可能とする（可用性重視）。
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Optional, Union

import threading
import time
import sounddevice as sd


class SDInput:
    """
    sounddevice RawInputStream + リングバッファ（16kHz/mono/PCM16）。

    どんなクラスか（責務/ユースケース）:
    - 低レイテンシで音声を取り込み、固定長のリングバッファに貯める薄いラッパ。
    - ストリームの生存監視を行い、上位でホットプラグ再初期化を判断できる情報を提供。

    主な処理:
    - `__init__`: 基本設定と内部バッファ/ロック/状態の初期化。
    - `_resolve_device`: 名称部分一致 → デバイス index 解決（入力デバイスのみ対象）。
    - `start()`: RawInputStream を生成して開始。コールバックで bytes をバッファへ積む。
    - `stop()`: ストリームが存在すれば安全に停止・解放。
    - `read_bytes()`/`pop_all()`: バッファ読み出しAPI。
    - `time_since_last_callback()`/`is_active()`: 生存監視ユーティリティ。
    """

    def __init__(self, sample_rate: int = 16000, block_ms: int = 20, max_ms: int = 5000) -> None:
        # 基本パラメータ
        self.sample_rate = sample_rate
        self.block_ms = block_ms
        # 1ブロックのサンプル数（例: 16kHz × 0.02s = 320）
        self.block_samples = int(self.sample_rate * (self.block_ms / 1000.0))
        self.bytes_per_sample = 2  # PCM16 は 2バイト/サンプル
        self.channels = 1
        self.dtype = "int16"

        # バッファと状態
        self.max_blocks = max(1, max_ms // self.block_ms)  # 保持上限ブロック数
        self._buf: Deque[bytes] = deque(maxlen=self.max_blocks)
        self._lock = threading.Lock()
        self._stream: Optional[sd.RawInputStream] = None
        self._last_cb_ts = 0.0  # 最終コールバック時刻（monotonic 秒）
        self._last_bytes = 0    # 直近の受信バイト数（デバッグ用）

    def _resolve_device(self, device: Optional[Union[int, str]]) -> Optional[int]:
        """デバイス指定を sounddevice 用 index に解決する。

        引数:
            device: None / int(index) / str(名称の部分一致)
        戻り値:
            解決できた index、もしくは None（デフォルト）
        例外:
            例外は握って None を返す（安定性重視）
        """
        if device is None or isinstance(device, int):
            return device
        # 文字列の場合は部分一致で検索（入力デバイスのみ対象）
        want = device.lower()
        try:
            devs = sd.query_devices()
        except Exception:
            return None
        candidates = [i for i, d in enumerate(devs) if d.get("max_input_channels", 0) > 0]
        for idx in candidates:
            name = str(devs[idx].get("name", "")).lower()
            if want in name:
                return idx
        return None

    def start(self, device: Optional[Union[int, str]] = None) -> None:
        """音声入力ストリームを開始。

        引数:
            device: None / 入力デバイス index / 名称の部分一致文字列
        処理の流れ（要約）:
            - 既存ストリームがあれば停止
            - コールバックを定義（例外は握り CallbackStop で停止指示）
            - デバイス解決後に RawInputStream を生成して開始
        """

        def callback(indata, frames, time_info, status):  # noqa: D401
            # I/Oスレッドから呼ばれるコールバック。ここで受信バイトをリングバッファへ積む。
            try:
                # 生存監視用に最終呼出時刻を更新
                self._last_cb_ts = time.monotonic()
                # under/overflow 等はログスパム回避のため捨てる
                if status:
                    pass
                # バッファ詰め（別スレッドからも安全なようロック）
                with self._lock:
                    b = bytes(indata)
                    self._last_bytes = len(b)
                    self._buf.append(b)
            except Exception:
                # コールバック内の例外はプロセスを落とさず停止指示のみ
                raise sd.CallbackStop

        # デバイス解決（部分一致→index）
        dev_idx = self._resolve_device(device)

        # 既存ストリームがあれば停止してから作り直す
        self.stop()
        # 生存監視メトリクスを初期化
        self._last_cb_ts = 0.0
        self._last_bytes = 0

        # 入力ストリームを生成
        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            blocksize=self.block_samples,
            callback=callback,
            device=dev_idx,
        )
        # 録音開始（PortAudio 内部スレッドが起動して callback が以後呼ばれる）
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
        """バッファをすべて取り出してクリアする（破壊的）。"""
        with self._lock:
            if not self._buf:
                return b""
            chunks = list(self._buf)
            self._buf.clear()
            return b"".join(chunks)

    # ---- liveness / 監視系ユーティリティ ----
    def time_since_last_callback(self) -> float:
        """最終コールバックからの経過秒（コールバック未実行なら +inf）。"""
        if self._last_cb_ts <= 0:
            return float("inf")
        return max(0.0, time.monotonic() - self._last_cb_ts)

    def is_active(self) -> bool:
        """ストリームが存在し active かどうか。"""
        return bool(self._stream is not None and getattr(self._stream, "active", False))

