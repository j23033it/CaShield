# ファイル/ディレクトリの役割一覧

このドキュメントは、本プロジェクト内の主なファイルが担う役割を簡潔にまとめたものです。

## ルート直下
- `README.md`: プロジェクトの概要、目的、セットアップ手順を記載。
- `TECHNOLOGIES.md`: 採用技術と各ライブラリの用途を説明。
- `FILES.md`: 本ファイル。各ファイル/ディレクトリの役割を一覧化。
- `requirements.txt`: 実行時（本番）に必要な最小依存のみを定義。
- `requirements-dev.txt`: 開発・テスト時にのみ必要な依存を定義（例: `pytest`、任意の再生補助）。
- `setup_and_test.py`: セットアップ（依存インストール）と基本動作確認（マイク、faster-whisper など）を自動実行。
- `main.py`: アプリのエントリーポイント。マイク入力→文字起こし→キーワード検知→警告音再生のループを実行。

## ディレクトリ
- `assets/`
  - `alert.wav`: 警告音のデフォルト音源。存在しない場合でもビープ音で代替。
- `config/`
  - `keywords.txt`: 検知対象のキーワード一覧（1 行 1 語）。
- `scripts/`
  - `create_alert_sound.py`: 簡易的なビープ音（WAV）を生成するスクリプト。
- `src/`
  - 本体ロジックを格納。
- `tests/`
  - 単体テスト群。主要クラス/関数の基本的な振る舞いを検証。

## src/ 配下
- `src/config.py`
  - アプリの設定値を一元管理。
  - 例: `WHISPER_MODEL`、`DEVICE`、`LANGUAGE`、`VAD_FILTER`、警告音パスなど。
- `src/models.py`
  - データモデル（`dataclass`）を定義。
    - `AudioData`: 録音バイト列とメタ情報（サンプルレート/チャンネル/時刻）。
    - `TranscriptionResult`: 文字起こし結果、信頼度、メタ情報、成功可否。
    - `AppConfig`: モデル名/言語などの設定表現。
- `src/audio_capture.py`
  - マイク入力（PyAudio）をバックグラウンドで取り込み、フレームを蓄積。
  - まとめて取得・クリア、長さ検証などのユーティリティを提供。
- `src/transcription.py`
  - `TranscriptionEngine` を提供。`faster_whisper.WhisperModel` を用いて音声（numpy 配列）を文字起こし。
  - バイト列（PCM16）を float32 [-1, 1] に正規化、モノラル化、推論、`TranscriptionResult` を返却。
- `src/action_manager.py`
  - トリガー検出時のアクション（警告音再生、簡易ログ出力）。
  - Windows では `winsound` で WAV を再生、非 WAV や他 OS では `pygame` / `playsound` を条件利用、失敗時はビープ音。
- `src/status_manager.py`
  - アプリ状態（IDLE/RECORDING/TRANSCRIBING/ERROR）のスレッドセーフな管理。
  - 現状は主にテストで使用され、本体ループへの統合は任意。
- `src/transcriber.py`
  - 単一関数 `transcribe(audio_path)` によるファイル入力 API の雛形。
  - 既存のメインループでは未使用（将来のファイル入力やバッチ処理向け）。

## tests/ 配下
- `tests/test_audio_capture.py`: `AudioCapture` の開始/停止/データ取得・短時間検知などをモックで検証。
- `tests/test_models.py`: `AudioData` の長さ計算、`TranscriptionResult` のデフォルト、`AppConfig` の dict 化を確認。
- `tests/test_status_manager.py`: `StatusManager` の基本操作とスレッドセーフ性を検証。
- `tests/test_transcription_engine.py`: 簡易ダミーによる文字起こしテスト（実装と差異があるため、参照時は調整を推奨）。

## 実行フロー（概要）
1. `main.py` 起動
2. `config/keywords.txt` のキーワードを読み込み
3. `pykakasi` でひらがな変換器を初期化
4. `TranscriptionEngine` でモデルロード（`faster-whisper`）
5. `AudioCapture` でマイク入力を開始（バックグラウンド）
6. 周期的に音声バッファを取り出し、文字起こし
7. ひらがな化したテキストに対し、キーワード部分一致で検知
8. 検知したら `ActionManager` が警告音を再生・ログ出力

## 設定の変更ポイント
- 文字起こしモデルや実行環境:
  - `src/config.py` の `WHISPER_MODEL`（例: `tiny`/`base`/`large-v3`）、`DEVICE`（`cpu`/`cuda`）、`COMPUTE_TYPE` を調整。
- 検知キーワード:
  - `config/keywords.txt` を編集（行追加/削除）。
- 音質・遅延調整:
  - `src/audio_capture.py` の `sample_rate`/`chunk_size` を初期化時に指定。
- 警告音の差し替え:
  - `assets/alert.wav` を任意の WAV に置換（Windows 以外や非 WAV の場合は追加依存の導入を検討）。

## 依存管理
- 実行時必要（本番）: `requirements.txt`（`faster-whisper`, `numpy`, `PyAudio`, `pykakasi`）。
- 開発/テストのみ: `requirements-dev.txt`（`pytest`, 任意の `pygame`/`playsound` など）。
