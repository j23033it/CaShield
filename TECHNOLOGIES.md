# 使用技術一覧

このプロジェクトで使用されている主要なライブラリ、モジュール、および技術について説明します。

## コア機能

| ライブラリ/モジュール | 概要 | 使用ファイル |
|---|---|---|
| **faster-whisper** | OpenAIのWhisperモデルを効率的に実行するためのライブラリ。ctranslate2をバックエンドとして使用し、高速な文字起こしを実現します。 | `src/transcription.py` |
| **ctranslate2** | Transformerモデルの高速な推論エンジン。本プロジェクトでは`faster-whisper`のバックエンドとして利用されています。 | `src/transcription.py` |
| **PyAudio** | マイクからのリアルタイム音声入力を取得するために使用されます。 | `src/audio_capture.py` |
| **pydub** | 警告音の再生や音声データの加工に使用される、高レベルな音声処理ライブラリです。 | `src/action_manager.py` |
| **pykakasi** | 認識された日本語テキストをひらがなに変換し、キーワード照合の精度を向上させるために使用されます。 | `main.py` |
| **pygame** | 警告音を再生するために使用されます。 | `src/action_manager.py` |

## 標準ライブラリ

| ライブラリ/モジュール | 概要 | 使用ファイル |
|---|---|---|
| **threading** | 音声の録音と文字起こし処理を並列で実行するために使用されます。 | `main.py` |
| **time** | 処理の待機やタイムスタンプの取得に使用されます。 | `main.py` |
| **os** | ファイルパスの操作や、設定ファイルの存在確認などに使用されます。 | `main.py` |
| **wave** | `PyAudio`で録音about:blank#blockedした音声データをWAV形式で一時的に保存するために使用されます。 | `src/audio_capture.py` |
| **datetime** | 検出ログにタイムスタンプを記録するために使用されます。 | `src/action_manager.py` |
| **warnings** | 特定の警告メッセージ（ctranslate2のUserWarningなど）を非表示にするために使用されます。 | `main.py` |

## テスト

| ライブラリ/モジュール | 概要 | 使用ファイル |
|---|---|---|
| **pytest** | プロジェクトの単体テストを作成・実行するためのフレームワークです。 | `tests/` ディレクトリ内の各ファイル |
