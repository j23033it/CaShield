### プロジェクト構成と各ファイルの役割

このドキュメントは、最新のディレクトリ構成と各ファイルの役割を簡潔に説明します。

## 全体構成（要約）

```
src/
  audio/sd_input.py      # 低レイテンシ音声入力（sounddevice）
  asr/dual_engine.py     # faster-whisper 二段ラッパ（FAST/FINAL）
  kws/fuzzy.py           # かな正規化 + rapidfuzz の KWS
  vad/webrtc.py          # WebRTC VAD による発話区間抽出
  action_manager.py      # 警告音・ログ処理（非ブロッキング）
  audio_capture.py       # PyAudioの簡易キャプチャ（従来互換）
  config.py              # 旧設定（一般項目）
  config/asr.py          # ASR 設定（コード内に集約: FAST/FINAL, VAD など）
  models.py              # データモデル（AudioData/TranscriptionResult）
  status_manager.py      # ステータス管理（スレッドセーフ）
  transcriber.py         # 単発音声の簡易トランスクライブAPI
  transcription.py       # TranscriptionEngine（faster-whisper 本体）
scripts/
  rt_stream.py           # リアルタイム監視のエントリ（VAD→ASR→KWS→アクション）
  create_alert_sound.py  # 簡易な警告音ファイル生成スクリプト
  llm_worker.py          # ログ監視とLLM要約ワーカ
webapp/
  app.py                 # Flask Webサーバ
  templates/             # HTMLテンプレート
  static/                # CSS, JSファイル
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
    - `keywords.py`: `keywords.txt` を解析し、キーワード一覧と深刻度マップを返す。
  - `config/`
    - `filter.py`: 既知ハルシネーション（定型文）の除外設定と判定関数
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
  - `llm_worker.py`: ログ監視とLLM要約ワーカ

- `webapp/`
  - `app.py`: Flask Webサーバ
  - `templates/`: HTMLテンプレート
  - `static/`: CSS, JSファイル

- `assets/`
  - `alert.wav`: デフォルトの警告音。存在しない場合はビープで代替。

- `config/`
  - `keywords.txt`: NGワード（レベル行形式推奨: `level2=[…]`, `level3=[…]`。後方互換で1行1語も可）

- `logs/`
  - 実行時出力のログ保管用（必要に応じて）。


---

## データフロー（リアルタイム → ログ → 要約 → 表示）

1. **音声入力**（`src/audio/sd_input.py`）  
   - sounddevice の `RawInputStream` で 16kHz/mono/PCM16 をチャンク収集（20–30ms）

2. **VAD**（`src/vad/webrtc.py`）  
   - WebRTC VAD（aggressiveness 0–3）またはフォールバックで発話区間を抽出  
   - 前後パディング（prev_ms / post_ms）、短ポーズ連結、最長長さ制限

3. **ASR**（`src/asr/dual_engine.py` / `src/transcription.py`）  
   - `faster-whisper`（CTranslate2）で日→日（`language="ja"`）認識  
   - 二段構成：FAST=`small(int8, beam=2)` / FINAL=`large-v3(int8, beam=5)`（コードで固定）

4. **KWS**（`src/kws/fuzzy.py`）  
   - かな正規化 + `rapidfuzz.partial_ratio` による**部分一致**（既定しきい値=88）。深刻度は `config/keywords.txt` のレベル定義に基づく。
   - 代表的なハルシネーション（配信締めのあいさつ等）はコードで除外

5. **原文ログ追記**（`scripts/rt_stream.py`）  
   - `logs/YYYY-MM-DD.txt` に `[YYYY-MM-DD HH:MM:SS] 客/店員: 発話 …` を1行追加  
   - **NGヒット時**は末尾に `[NG: キーワード]` を付与（→ LLM検知のアンカー）
   - FAST/FINAL の双方で、`src/config/filter.py` 定義の禁止フレーズはスキップ

6. **LLM要約**（`scripts/llm_worker.py` + `src/llm/*`）  
   - 原文ログを監視し、NG行を基点に**窓取り**（min_sec≥12 / max_sec≤30 / tokens≤1024）  
   - **構造化JSON**を生成：`{ ng_word, turns[], summary, severity(1–5), action }`（severity は keywords.txt の既定値を採用）
   - `logs/summaries/<date>.jsonl` に**1 NG 事象＝1行**で追記  
   - 失敗は `logs/summaries/<date>.errors.log` と `logs/summaries/errors/*.log` に保存

7. **Web表示**（`webapp/app.py`）  
   - `/` … 日付一覧  
   - `/logs/<date>` … 原文表示（初回ロードで全件表示し、SSE `/stream/<date>` で追記。追記時に通知音）  
   - `/api/logs/<date>` … 原文のJSON配列  
   - （要約ビューは今後 `/summaries/<date>` でのカード表示に対応予定の設計）

---

## ログ・ファイル形式

### 要約（`logs/summaries/<date>.jsonl`）
- 1 NG 事象につき **1行の JSON**  
- 例（概略）：
```json
{
  "date": "2025-08-20",
  "anchor_time": "13:05:11",
  "ng_word": "無能",
  "turns": [{"role":"customer","text":"…","time":"13:05:11"}, ...],
  "summary": "…",
  "severity": 3,
  "action": "…",
  "meta": {"model":"gemini-1.5-flash-latest","line_range":[345,359], ...}
}


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


