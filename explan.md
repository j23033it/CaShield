### プロジェクト構成と各ファイルの役割

このドキュメントは、最新のディレクトリ構成と各ファイルの役割を簡潔に説明します。

## 全体構成（要約）

```
src/
  audio/sd_input.py      # 低レイテンシ音声入力（sounddevice）
  asr/engine.py          # faster-whisper ラッパ
  kws/simple.py          # ひらがな化＋部分一致の簡易KWS
  vad/webrtc.py          # WebRTC VAD による発話区間抽出
  action_manager.py      # 警告音・ログ処理（非ブロッキング）
  audio_capture.py       # PyAudioの簡易キャプチャ（従来互換）
  config.py              # ASRや動作の基本設定
  models.py              # データモデル（AudioData/TranscriptionResult）
  status_manager.py      # ステータス管理（スレッドセーフ）
  transcriber.py         # 単発音声の簡易トランスクライブAPI
  transcription.py       # TranscriptionEngine（faster-whisper 本体）
scripts/
  rt_stream.py           # リアルタイム監視のエントリ（VAD→ASR→KWS→アクション）
  create_alert_sound.py  # 簡易な警告音ファイル生成スクリプト
assets/alert.wav         # 警告音のデフォルトファイル
config/keywords.txt      # NGワード一覧（1行1語）
logs/                    # 検出ログの出力（必要に応じて）
main.py                  # シンプル実行のエントリポイント
README.md, TECHNOLOGIES.md, requirements.txt
```

## ディレクトリの役割

- `src/`
  - アプリ本体のコードを集約するルートパッケージ。
  - `audio/`
    - `sd_input.py`: sounddevice の `RawInputStream` による低レイテンシ入力。リングバッファで 20–30 ms 単位のチャンク化。
  - `asr/`
    - `engine.py`: `faster-whisper` を使った軽量ラッパ。PCM16バイト列を float32 に変換して `model.transcribe()` を実行。
  - `kws/`
    - `simple.py`: 認識テキストをひらがな化し、`keywords.txt` の各語と部分一致で照合。
  - `vad/`
    - `webrtc.py`: WebRTC VAD を使った発話区間抽出器。前後パディングや短ポーズ連結を実装。
  - ルート直下
    - `action_manager.py`: 検出時の警告音再生・ログを非ブロッキングに実行。
    - `audio_capture.py`: PyAudio による簡易録音（互換・学習用）。
    - `config.py`: モデル名・デバイス・量子化などの基本設定。
    - `models.py`: 音声データと結果のデータクラス定義。
    - `status_manager.py`: スレッドセーフな状態管理。
    - `transcriber.py`: ファイル/バイト列入力の簡易文字起こしヘルパ。
    - `transcription.py`: `TranscriptionEngine`（モデルのロードと推論）。

- `scripts/`
  - `rt_stream.py`: ランタイム構成（`sd_input`→`webrtc VAD`→`ASR`→`KWS`→アクション）。
  - `create_alert_sound.py`: 簡易な警告音（wav）を生成。

- `assets/`
  - `alert.wav`: デフォルトの警告音。存在しない場合はビープで代替。

- `config/`
  - `keywords.txt`: NGワード。任意で `config.yaml` を置くと追加設定を読み込み。

- `logs/`
  - 実行時出力のログ保管用（必要に応じて）。

## ルートの主なファイル

- `main.py`
  - シンプルな監視エントリ。3秒ごとにバッファを取り出して ASR→KWS→アクションを実行。
- `README.md`
  - プロジェクト概要・セットアップ・実行方法。
- `TECHNOLOGIES.md`
  - 使用技術の一覧と使用箇所。
- `requirements.txt`
  - 依存ライブラリ。
- `setup_and_test.py`
  - 初期セットアップ/動作確認用（任意）。

## 実行の最短手順（再掲）

```bash
source venv/bin/activate
# シンプル実行
python main.py
# リアルタイム監視（推奨）
python scripts/rt_stream.py
```


