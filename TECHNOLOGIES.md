# 使用技術一覧

本プロジェクトの主要技術と使用箇所をまとめます。

## コアライブラリ

| ライブラリ/モジュール | 概要 | 主な使用ファイル |
|---|---|---|
| faster-whisper | Whisper を CTranslate2 バックエンドで高速実行 | `src/asr/engine.py`, `src/transcription.py` |
| CTranslate2 | 高速推論エンジン（faster-whisper のバックエンド） | 〃 |
| sounddevice | 低レイテンシ音声入力（RawInputStream） | `src/audio/sd_input.py`, `scripts/rt_stream.py` |
| PyAudio | 簡易キャプチャ実装（互換用途） | `src/audio_capture.py` |
| webrtcvad | 音声区間検出（VAD） | `src/vad/webrtc.py`, `scripts/rt_stream.py` |
| pykakasi | ひらがな変換（KWS 用） | `src/kws/simple.py`, `main.py` |
| pygame / winsound | 警告音の再生 | `src/action_manager.py` |

## 標準ライブラリ

| ライブラリ | 用途 | 主な使用ファイル |
|---|---|---|
| threading | 録音スレッド/非同期処理 | `src/audio_capture.py`, `main.py` |
| time / datetime | 計測・タイムスタンプ | `scripts/rt_stream.py`, `src/action_manager.py` |
| os / pathlib | ファイル/環境変数 | `scripts/rt_stream.py`, `main.py` |
| warnings | 既知の警告抑制 | `main.py` |

## 備考

- CPU 環境では `compute_type=int8` により高速化。
- GPU (CUDA) 環境では `device=cuda`, `compute_type=float16` を推奨。
