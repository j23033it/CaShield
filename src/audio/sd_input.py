"""
音声入力モジュール（sounddevice ラッパー）

このモジュールは、PortAudio バックエンドを使う `sounddevice.RawInputStream` を利用して、
16kHz・モノラル・PCM16 形式の音声を低レイテンシ（デフォルト 20ms ブロック）で取得し、
リングバッファ（deque）に蓄積・取り出しするためのユーティリティクラス `SDInput` を提供します。

ポイント:
- .env は使わず、コード内設定で運用（サンプリング・ブロック長など）。
- コールバック（I/Oスレッド）で受け取った生バイトをそのまま `deque` に積み、
  メインループ側から `pop_all()` でまとめて取得します。
- 例外は極力握って落ちないようにし、用途はリアルタイム監視に特化しています。
"""

from collections import deque
from typing import Deque, Optional
import time

import numpy as np
import sounddevice as sd


class SDInput:
    """
    sounddevice RawInputStream + リングバッファ（16kHz/mono/PCM16）。

    どんなクラスか:
    - 低レイテンシで音声を取り込み、固定長のリングバッファに貯める薄いラッパです。

    どんな処理をしているか:
    - `__init__`: サンプリング・ブロック長などの基本設定と、内部バッファ（deque）を準備。
    - `start()`: RawInputStream を生成し、コールバックで bytes を `deque` に詰める。
    - `stop()`: ストリームがあれば安全に停止・解放する。
    - `read_bytes()`: バッファの内容を連結して返す（バッファは保持）。
    - `pop_all()`: バッファの内容を連結して返し、バッファをクリア（破壊的）。
    """

    def __init__(self, sample_rate: int = 16000, block_ms: int = 20, max_ms: int = 5000) -> None:
        # 取り込み設定（既定は 16kHz/mono/PCM16、20ms ブロック）
        self.sample_rate = sample_rate  # サンプリング周波数（Hz）
        self.block_ms = block_ms        # コールバック単位の時間（ミリ秒）
        # 1 ブロックで扱うサンプル数（例: 16kHz × 0.02s = 320 サンプル）
        self.block_samples = int(self.sample_rate * (self.block_ms / 1000.0))
        self.bytes_per_sample = 2       # PCM16 は 2 バイト/サンプル
        self.channels = 1               # モノラル固定
        self.dtype = "int16"            # 取り込みデータ型
        # バッファに保持する最大ブロック数（max_ms に応じた固定長リング）
        # 例: max_ms=5000, block_ms=20 → 最大 250 ブロック保持
        self.max_blocks = max(1, max_ms // self.block_ms)
        self._buf: Deque[bytes] = deque(maxlen=self.max_blocks)  # 音声チャンクを積むリングバッファ
        self._stream: Optional[sd.RawInputStream] = None         # 実体の入力ストリーム
        self._last_cb_ts: Optional[float] = None                 # 直近のコールバック時刻（liveness 判定用）

    def start(self, device: Optional[int] = None) -> None:
        """音声入力ストリームを開始する。

        引数:
            device: 入力デバイスの index（None の場合は OS 既定）。
        挙動:
            RawInputStream のコールバックで受信した生 PCM を bytes にしてリングバッファへ追加します。
            I/O スレッド起因の軽微なステータスは捨て、オーバーフロー時も極力継続します。
        """
        def callback(indata, frames, time_info, status):  # noqa: D401
            # PortAudio（I/Oスレッド）から定期的に呼ばれる。frames は block_samples 近辺。
            # indata: Cバッファ上のPCM16生データ、frames: サンプル数、time_info/status: 実行メタ情報
            if status:
                # 例: underflow/overflow 等。ここではログスパムを避け、捨てる（継続運転重視）。
                # 必要に応じて status を監視し、しきい値で再初期化する運用にも対応可能。
                pass
            # PCM16 の C バッファを Python の bytes にパックして追記
            # bytes() はバッファコピーを伴うが、20ms単位なら負荷は軽微
            self._buf.append(bytes(indata))
            # liveness: 最終コールバック時刻を記録
            self._last_cb_ts = time.perf_counter()

        # 指定デバイス（またはデフォルト）で RawInputStream を作成
        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            blocksize=self.block_samples,
            callback=callback,
            device=device,
        )
        # 録音開始（PortAudio内部スレッドが起動して callback が以後呼ばれる）
        self._stream.start()

    def stop(self) -> None:
        """ストリームが存在する場合は安全に停止/解放する（例外は握る）。"""
        if self._stream is not None:
            try:
                # ポーリング停止（callback 呼び出しが止まる）
                self._stream.stop()
                # PortAudioのリソース開放
                self._stream.close()
            except Exception:
                # 停止・解放が失敗しても上位の再初期化で継続できるよう握る
                pass
        # 参照を外してGCに委ねる
        self._stream = None

    def read_bytes(self) -> bytes:
        """バッファの内容を連結して返す（読み出し後もバッファは保持）。"""
        # deque は可変だが、join の間に callback が走っても致命的な破損は起きない前提で運用
        # 厳密な一貫性が必要な場合はロックを導入する
        return b"".join(self._buf)

    def pop_all(self) -> bytes:
        """バッファの内容を連結して返し、内部バッファをクリア（破壊的）。"""
        # 取り出し側（メインループ）で周期的に呼び出し、VAD など後段へ渡す
        if not self._buf:
            # 何も溜まっていなければ空バイト列
            return b""
        # 現在の要素をリスト化してスナップショットを作る
        chunks = list(self._buf)
        # バッファを空にして次の蓄積に備える
        self._buf.clear()
        # チャンク群を連結（PCM16の連結なので後段でそのまま扱える）
        return b"".join(chunks)

    # --- 追加: ホットプラグ検知用の補助API ---
    def time_since_last_callback(self) -> float:
        """最後に PortAudio コールバックが呼ばれてからの経過秒を返す。

        どんな関数か:
        - liveness チェック用の単純な経過時間を提供します。未開始時など記録が無い場合は大きな値を返します。
        """
        if self._last_cb_ts is None:
            return 1e9
        return max(0.0, time.perf_counter() - self._last_cb_ts)

    def is_active(self) -> bool:
        """ストリームが存在するかの簡易判定（PortAudio内部状態には依存しない）。"""
        return self._stream is not None



