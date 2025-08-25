import pyaudio
from threading import Thread, Event
from typing import Optional
from src.models import AudioData


class AudioCapture:
    """
    オーディオキャプチャを行うクラス
    """
    def __init__(self, sample_rate=16000, channels=1, chunk_size=1024):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.format = pyaudio.paInt16
        # 初期のPyAudioインターフェイス
        self._audio_interface = pyaudio.PyAudio()
        self._stream = None
        # キャプチャデータを保持するバッファ
        self._frames = []
        # 録音中フラグ
        self._running = Event()

    def start_capture(self):
        """
        オーディオキャプチャを開始。既存データをクリアし、
        新しいPyAudioインターフェイスを生成します。
        """
        # フレームバッファをクリア
        self._frames = []
        # 新しいPyAudioインターフェイスを生成
        self._audio_interface = pyaudio.PyAudio()
        try:
            print(f"[デバッグ] マイク設定: サンプルレート={self.sample_rate}, チャンネル={self.channels}, チャンクサイズ={self.chunk_size}")
            self._stream = self._audio_interface.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )
            print("[デバッグ] マイクの初期化が完了しました")
        except Exception as e:
            raise RuntimeError(f"マイクが開けませんでした: {e}")

        # 録音ループを開始
        self._running.set()
        def _capture_loop():
            print("[デバッグ] 音声キャプチャループを開始します")
            frame_count = 0
            while self._running.is_set():
                try:
                    data = self._stream.read(
                        self.chunk_size, exception_on_overflow=False
                    )
                    self._frames.append(data)
                    frame_count += 1
                    if frame_count % 100 == 0:  # 100フレームごとにデバッグ出力
                        print(f"[デバッグ] {frame_count}フレーム取得済み")
                except Exception as e:
                    print(f"[デバッグ] 音声読み取りエラー: {e}")
                    break

        # バックグラウンドでキャプチャ
        self._thread = Thread(target=_capture_loop, daemon=True)
        self._thread.start()

    def stop_capture(self):
        """
        オーディオキャプチャを停止。ストリームを閉じ、
        録音スレッドを終了させます。
        """
        # 受信ループ停止
        self._running.clear()
        # ストリーム停止・クローズ
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
        # スレッド終了待ち（タイムアウト付き）
        if hasattr(self, "_thread") and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        # ※ PyAudioインターフェイスは破棄せず再利用可能に

    def get_audio_data(self) -> bytes:
        """
        キャプチャ済みのバイト列を返す
        """
        return b"".join(self._frames)
    
    def get_audio_data_object(self) -> AudioData:
        """
        キャプチャ済みのデータをAudioDataオブジェクトとして返す
        """
        raw_bytes = self.get_audio_data()
        return AudioData(
            raw_bytes=raw_bytes,
            sample_rate=self.sample_rate,
            channels=self.channels
        )

    def get_and_clear_audio_data_object(self) -> Optional[AudioData]:
        """
        キャプチャ済みのデータをAudioDataオブジェクトとして返し、内部バッファをクリアする
        """
        if not self._frames:
            return None
        
        # バッファをコピーしてクリア
        frames_to_process = self._frames[:]
        self._frames.clear()
        
        raw_bytes = b"".join(frames_to_process)
        print(f"[デバッグ] バッファから {len(frames_to_process)}フレーム取得, 合計{len(raw_bytes)}バイト")
        
        return AudioData(
            raw_bytes=raw_bytes,
            sample_rate=self.sample_rate,
            channels=self.channels
        )

    def validate(self, min_duration_sec=0.5):
        """
        録音時間が最低値を満たすか検証
        """
        raw = self.get_audio_data()
        # PCM16: 2バイト／サンプル
        total_samples = len(raw) // (2 * self.channels)
        duration = total_samples / self.sample_rate
        if duration < min_duration_sec:
            raise ValueError(f"録音時間が短すぎます: {duration:.2f}s")
