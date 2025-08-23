#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
バックエンド処理を統合したモノリシックファイル。

- リアルタイムでの音声入力、音声区間検出、文字起こし
- NGワードの検出と、それに応じたアクション（警告音、ログ記録）の実行

実行方法:
    リポジトリのルートから `python backend.py` を実行してください。
"""

# --- 標準ライブラリのインポート ---
from __future__ import annotations
import os
import sys
import time
import wave
import threading
import collections
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Generator, Iterable, Deque

# --- 外部ライブラリのインポート ---
try:
    import yaml
    import numpy as np
    import sounddevice as sd
    import webrtcvad
    from faster_whisper import WhisperModel
    from pykakasi import kakasi
except ImportError as e:
    print(f"エラー: 依存ライブラリがインストールされていません ({e.name}).", file=sys.stderr)
    print("pip install -r requirements.txt を実行してください。", file=sys.stderr)
    sys.exit(1)

# =============================================================================
# --- グローバル定数定義 ---
# =============================================================================

ROOT_DIR = Path(__file__).resolve().parent
LOG_DIR = ROOT_DIR / "logs"
CONFIG_DIR = ROOT_DIR / "config"
ASSETS_DIR = ROOT_DIR / "assets"

BANNED_HALLUCINATIONS = {
    "ご視聴ありがとうございました", "ご視聴ありがとうございました。",
    "チャンネル登録よろしくお願いします", "チャンネル登録よろしくお願いします。",
}

# =============================================================================
# --- 元 `src/action_manager.py` の内容 ---
# 警告音の再生やログ記録など、検知後のアクションを管理
# =============================================================================

class ActionManager:
    """NGワード検出時のアクション（警告音再生など）を管理するクラス"""
    def __init__(self, sound_file: Optional[str] = None):
        self.sound_file = sound_file
        self.wav_data = None
        if self.sound_file and os.path.exists(self.sound_file):
            try:
                with wave.open(self.sound_file, 'rb') as wf:
                    self.wav_data = wf.readframes(wf.getnframes())
                    self.samplerate = wf.getframerate()
                    self.channels = wf.getnchannels()
            except Exception as e:
                print(f"[警告] 音声ファイルの読み込みに失敗: {e}", file=sys.stderr)
                self.wav_data = None

    def _play_in_thread(self):
        if self.wav_data:
            try:
                sd.play(np.frombuffer(self.wav_data, dtype=np.int16), self.samplerate, blocking=True)
            except Exception as e:
                print(f"[エラー] 音声の再生に失敗: {e}", file=sys.stderr)
        else:
            # フォールバックとしてビープ音（環境依存）
            print("\a", end="", flush=True)
            time.sleep(0.5)

    def play_warning(self):
        """警告音を非同期で再生する"""
        threading.Thread(target=self._play_in_thread, daemon=True).start()

# =============================================================================
# --- 元 `src/audio/sd_input.py` の内容 ---
# sounddeviceを用いた低遅延マイク入力
# =============================================================================

class SDInput:
    """sounddeviceのRawInputStreamを利用した低遅延マイク入力"""
    def __init__(self, sample_rate: int = 16000, block_ms: int = 30, channels: int = 1):
        self.sample_rate = sample_rate
        self.block_size = (sample_rate * block_ms) // 1000
        self.channels = channels
        self.stream: Optional[sd.RawInputStream] = None
        self.buffer: Deque[bytes] = collections.deque()
        self.lock = threading.Lock()

    def _callback(self, indata: bytes, frames: int, time_info, status) -> None:
        if status:
            print(f"[マイク入力] ステータス: {status}", file=sys.stderr)
        with self.lock:
            self.buffer.append(indata)

    def start(self, device: Optional[str | int] = None) -> None:
        if self.stream is not None:
            return
        try:
            self.stream = sd.RawInputStream(
                samplerate=self.sample_rate, blocksize=self.block_size, device=device,
                channels=self.channels, dtype='int16', callback=self._callback)
            self.stream.start()
            print(f"[マイク入力] マイク監視を開始しました (デバイス: {device or 'デフォルト'})")
        except Exception as e:
            print(f"[マイク入力] ストリームの開始に失敗: {e}", file=sys.stderr)
            self.stream = None

    def stop(self) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            print("[マイク入力] マイク監視を停止しました")

    def pop_all(self) -> Optional[bytes]:
        with self.lock:
            if not self.buffer:
                return None
            data = b''.join(list(self.buffer))
            self.buffer.clear()
            return data

# =============================================================================
# --- 元 `src/vad/webrtc.py` の内容 ---
# WebRTC VADを用いた音声区間検出
# =============================================================================

class WebRTCVADSegmenter:
    """WebRTC VADを利用して発話区間を検出する"""
    def __init__(self, sample_rate: int = 16000, frame_ms: int = 30, aggressiveness: int = 3, prev_ms: int = 200, post_ms: int = 300):
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.vad = webrtcvad.Vad(aggressiveness)
        self.bytes_per_frame = (sample_rate * frame_ms // 1000) * 2
        self.prev_buffer_count = prev_ms // frame_ms
        self.post_buffer_count = post_ms // frame_ms
        self.prev_buffer: Deque[bytes] = collections.deque(maxlen=self.prev_buffer_count)
        self.triggered = False
        self.speech_buffer: List[bytes] = []
        self.post_countdown = 0

    def feed(self, chunk: bytes) -> Generator[bytes, None, None]:
        for i in range(0, len(chunk), self.bytes_per_frame):
            frame = chunk[i:i+self.bytes_per_frame]
            if len(frame) < self.bytes_per_frame:
                continue
            is_speech = self.vad.is_speech(frame, self.sample_rate)
            if self.triggered:
                self.speech_buffer.append(frame)
                if not is_speech:
                    self.post_countdown -= 1
                    if self.post_countdown <= 0:
                        self.triggered = False
                        yield b''.join(self.speech_buffer)
                        self.speech_buffer.clear()
                else:
                    self.post_countdown = self.post_buffer_count
            else:
                if is_speech:
                    self.triggered = True
                    self.speech_buffer.extend(self.prev_buffer)
                    self.speech_buffer.append(frame)
                    self.post_countdown = self.post_buffer_count
                else:
                    self.prev_buffer.append(frame)

# =============================================================================
# --- 元 `src/asr/engine.py` の内容 ---
# faster-whisperを用いた文字起こしエンジン
# =============================================================================

class FasterWhisperEngine:
    """faster-whisperのラッパークラス"""
    def __init__(self, model_name: str, device: str, compute_type: str, language: str, beam_size: int, condition_on_previous_text: bool, vad_filter: bool, initial_prompt: str):
        try:
            self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
        except Exception as e:
            print(f"[ASR] モデルのロードに失敗: {e}", file=sys.stderr)
            print(f"    - モデル名: {model_name}, デバイス: {device}, 計算タイプ: {compute_type}", file=sys.stderr)
            sys.exit(1)
        self.params = {
            "language": language, "beam_size": beam_size,
            "condition_on_previous_text": condition_on_previous_text,
            "vad_filter": vad_filter, "initial_prompt": initial_prompt or None,
            "log_prob_threshold": -0.8, "no_speech_threshold": 0.6
        }

    def _pcm16_to_float32(self, pcm16: bytes) -> np.ndarray:
        return np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0

    def transcribe_stream(self, frames: Iterable[bytes]) -> Generator[Dict, None, None]:
        for chunk in frames:
            if not chunk: continue
            audio = self._pcm16_to_float32(chunk)
            segments, _ = self.model.transcribe(audio, **self.params)
            text = "".join(seg.text for seg in segments)
            yield {"type": "final", "text": text}

# =============================================================================
# --- 元 `src/kws/simple.py` の内容 ---
# テキストベースの簡易キーワードスポッティング
# =============================================================================

class SimpleKWS:
    """ひらがな化と部分一致による簡易キーワード検出"""
    def __init__(self, keywords: List[str]):
        self.kks = kakasi()
        self.target_words_original = keywords
        self.target_words_hira = [self._convert_to_hiragana(w) for w in keywords]

    def _convert_to_hiragana(self, text: str) -> str:
        return "".join([item['hira'] for item in self.kks.convert(text)])

    def detect(self, text: str) -> List[str]:
        if not text: return []
        text_hira = self._convert_to_hiragana(text)
        return [self.target_words_original[i] for i, hira_word in enumerate(self.target_words_hira) if hira_word in text_hira]

# =============================================================================
# --- 元 `scripts/rt_stream.py` の内容 ---
# メインの実行ロジック
# =============================================================================

def _write_log_line(role: str, text: str, hits: List[str]) -> None:
    """Webフロントが監視する形式でログファイルに追記する"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    who = "店員" if role == "clerk" else "客"
    ng = f" [NG: {', '.join(hits)}]" if hits else ""
    line = f"[{ts}] {who}: {text}{ng}\n"
    (LOG_DIR / f"{date}.txt").open("a", encoding="utf-8").write(line)

def load_keywords(path: Path) -> List[str]:
    """キーワードファイルを読み込む"""
    if not path.exists(): return ["土下座", "無能", "死ね"]
    with path.open("r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def run_streamer() -> None:
    """リアルタイム監視のメイン処理"""
    cfg_path = CONFIG_DIR / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    cfg = cfg or {}

    sample_rate = int(cfg.get("sample_rate", 16000))
    block_ms = int(cfg.get("block_ms", 30))
    vcfg = cfg.get("vad", {}) or {}
    acfg = cfg.get("asr", {}) or {}

    sd_in = SDInput(sample_rate=sample_rate, block_ms=block_ms)
    vad = WebRTCVADSegmenter(sample_rate=sample_rate, frame_ms=block_ms, aggressiveness=int(vcfg.get("aggressiveness", 2)), prev_ms=int(vcfg.get("pad_prev_ms", 200)), post_ms=int(vcfg.get("pad_post_ms", 300)))
    asr = FasterWhisperEngine(model_name=acfg.get("model", "tiny"), device=acfg.get("device", "cpu"), compute_type=acfg.get("compute_type", "int8"), language="ja", beam_size=int(acfg.get("beam_size", 3)), condition_on_previous_text=False, vad_filter=True, initial_prompt=acfg.get("initial_prompt", ""))
    keywords = load_keywords(CONFIG_DIR / "keywords.txt")
    kws = SimpleKWS(keywords)
    action_mgr = ActionManager(str(ASSETS_DIR / "alert.wav"))

    print("=" * 50)
    print("CaShieldリアルタイム監視システム - 起動")
    print(f"  - モデル: {acfg.get('model', 'tiny')}, デバイス: {acfg.get('device', 'cpu')}")
    print(f"  - NGワード: {', '.join(keywords)}")
    print("Ctrl+C で停止します\n")

    sd_in.start(device=os.environ.get("CASHIELD_INPUT_DEVICE"))

    try:
        while True:
            time.sleep(0.06)
            chunk = sd_in.pop_all()
            if not chunk: continue
            utterances = vad.feed(chunk)
            for utt in utterances:
                eos_t = time.perf_counter()
                utt_ms = len(utt) / (sample_rate * 2) * 1000.0
                asr_t0 = time.perf_counter()
                texts = [out.get("text", "") for out in asr.transcribe_stream([utt]) if out.get("type") == "final"]
                text = "".join(texts).strip()

                if text in BANNED_HALLUCINATIONS:
                    print(f"[フィルタ] 幻覚を検出、無視します: {text}")
                    continue

                asr_t1 = time.perf_counter()
                hits = kws.detect(text)
                print(f"[発話 {utt_ms:.0f}ms] asr={(asr_t1 - asr_t0)*1000:.0f}ms | {text}", flush=True)
                _write_log_line(role="customer", text=text, hits=hits)
                if hits:
                    print(f"!! NGワード検出: {hits}", flush=True)
                    action_mgr.play_warning()
    except KeyboardInterrupt:
        print("\nユーザ操作により停止します。")
    finally:
        sd_in.stop()
        print("監視を終了しました。")

# =============================================================================
# --- 実行ブロック ---
# =============================================================================

if __name__ == "__main__":
    # このファイルは直接実行されることを想定
    run_streamer()
