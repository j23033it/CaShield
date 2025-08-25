---

### `TECHNOLOGIES.md`（全文）

```markdown
# 使用技術一覧（最新版）

本プロジェクトで利用している主要技術と使用箇所をまとめます。  
**実行フロー**：`sounddevice` → `WebRTC VAD` → `faster-whisper（二段: FAST/FINAL）` → `KWS（かな正規化 + rapidfuzz 部分一致）` → 原文ログ → **Gemini 要約** → Web 表示（SSE）

---

## コアライブラリ

| ライブラリ/モジュール | 概要 | 主な使用ファイル |
|---|---|---|
| **faster-whisper** | Whisper を CTranslate2 バックエンドで高速実行（FAST/FINAL 二段） | `src/asr/dual_engine.py`, `src/transcription.py` |
| **CTranslate2** | 高速推論エンジン（faster-whisper のバックエンド） | 〃 |
| **sounddevice** | 低レイテンシ音声入力（RawInputStream） | `src/audio/sd_input.py`, `scripts/rt_stream.py` |
| **webrtcvad** | 音声区間検出（VAD）／無い場合はフォールバック | `src/vad/webrtc.py`, `scripts/rt_stream.py` |
| **pykakasi / rapidfuzz** | かな正規化 + fuzzy 部分一致（KWS 前処理・判定） | `src/kws/fuzzy.py` |
| **Flask** | Web API / テンプレート / SSE（ログの追記配信） | `webapp/app.py`, `webapp/templates/*` |
| **google-genai** | Gemini クライアント（構造化JSON生成） | `src/llm/client_gemini.py` |
| **python-dotenv** | `.env` 読み込み（APIキー等の秘匿設定） | `src/llm/client_gemini.py` |

> 備考：`pygame / winsound` を使う構成もありますが、現行は `action_manager.py` による警告音再生（OS依存）で簡素化しています。

---

## 標準 / 周辺ライブラリ

| ライブラリ | 用途 | 主な使用ファイル |
|---|---|---|
| **threading** / **asyncio** | 録音スレッド / LLMワーカの非同期処理 | `scripts/rt_stream.py`, `scripts/llm_worker.py` |
| **time / datetime** | 計測・タイムスタンプ・アンカー時刻 | `scripts/rt_stream.py`, `src/llm/queue.py` |
| **os / pathlib** | ファイル・環境変数 | 全般 |
| **json** | JSONL入出力 | `src/llm/queue.py`, Web API |
| — | — | — |
| **numpy** | PCM16→float32 変換など | `src/transcription.py`, VADフォールバック |

---

## モデル・推論設定の目安

- **CPU 環境**：`device=cpu` / `compute_type=int8`（既定）  
- **GPU（CUDA）**：`device=cuda` / `compute_type=float16` を推奨  
- **ASR 設定（コード内）**：`src/config/asr.py` に FAST/FINAL のモデル・ビーム・VAD 等を集約  
  - FAST = `small (int8, beam=2)` / FINAL = `large-v3 (int8, beam=5)`（既定）  
- **Gemini モデル**：`CASHIELD_GEMINI_MODEL`（例：`gemini-2.5-flash-lite`）を `.env` で指定

---

## I/O とプロトコル

- **音声**：16kHz / mono / PCM16（bytes）  
- **原文ログ**：LF区切りのプレーンテキスト（1行1発話）。`[NG: …]` マークを基点に LLM が窓取り  
- **要約**：JSONL（1 NG 事象 ≒ 1 行）。`{ ng_word, turns[], summary, severity(1–5), action, meta }`  
- **Web**：Flask（HTMLテンプレート）＋ SSE `/stream/<date>` によるログ追記配信  
  - 初回ロードで過去ログを全件表示し、以降の追加行をSSEでリアルタイムに追記（追記時に通知音）

---

## OS 依存コンポーネント

- **PortAudio**（sounddevice）  
  - Raspberry Pi: `sudo apt install portaudio19-dev`  
  - Windows: pip のみで OK（バイナリ配布）  
- **FFmpeg**（ASR 前処理や変換に利用する場合）  
  - Raspberry Pi: `sudo apt install ffmpeg`  
  - Windows: 任意導入（パス設定）



## セキュリティ・運用

- **秘密鍵**は `.env` に保存し、**Git 管理しない**（`.gitignore` に登録）  
- `.env` は **`python-dotenv`** によって自動読込。既存の環境変数は上書きしないため、**空の環境変数が残っていると `.env` が効かない**ことに注意  
- 長期運用は **systemd**（Raspberry Pi）で `rt_stream` / `app.py` / `llm_worker` をそれぞれ常駐化

---

## 環境変数（.env）による設定

`.env` ファイルで以下の項目を設定できます。

- **`CASHIELD_GEMINI_MODEL=gemini-2.5-flash-lite`**
  - **意味**: 利用する Gemini モデル名。軽量モデルは高速・安価ですが、精度は標準的です。
  - **変更理由**: より高精度が必要な場合（例: `gemini-2.5-pro`）や、さらに軽量化したい場合に調整します。
  - **推奨値**: 現場での常時監視など、速度とコストを重視する場合は `gemini-2.5-flash-lite` のままが適しています。

- **`CASHIELD_LLM_TEMP=0.1`**
  - **意味**: 温度（出力のランダム性）。0に近いほど事実ベースで安定し、高いほど表現が多様化します。
  - **使い分け**: 要約は安定性重視のため `0.0`〜`0.2` が推奨されます（`0.1`は適切）。

- **`CASHIELD_MIN_SEC=12`**
  - **意味**: NG検知を中心に、LLMに渡す会話の最小秒数。
  - **狙い**: 短すぎるコンテキストによる誤解釈を防ぎます。12秒以上を確保することで誤判定を抑制します。

- **`CASHIELD_MAX_SEC=30`**
  - **意味**: 1回の要約対象とする会話の最大秒数。
  - **狙い**: 長すぎる場合に発生する遅延やコスト増を抑え、文脈と性能のバランスを取ります。

- **`CASHIELD_MAX_TOKENS=512`**
  - **意味**: LLMに渡すプロンプトの最大トークン数（文字数上限のイメージ）。
  - **狙い**: 極端に長い会話を適切に切り詰めて、APIエラーや過剰なコストを防ぎます。
  - **補足**: 窓取り処理は「発話単位を連結しながら `min_sec` を満たし、`max_sec` と `max_tokens` を超えない範囲」でコンテキストを構築します。
狙い：30秒上限で、文脈は確保しつつ速度/費用をコントロール。

5) CASHIELD_MAX_TOKENS=512

意味：LLM に渡すトークンの上限（文字数上限のイメージ）。

狙い：極端に長い会話を切り詰めて投入。

目安：512トークン ≒ 数百〜千数百文字程度（日本語だと内容により変動）。

補足：窓取りは「発話単位を足しながら min_sec を満たし、max_sec と max_tokens を超えないよう調整」します。


| 区分             | モデル名                        | API指定ID（例）                                                                             | ステータス          | 主な用途/特徴         | 無料枠（Free Tier）の上限\*                          |
| -------------- | --------------------------- | -------------------------------------------------------------------------------------- | -------------- | --------------- | -------------------------------------------- |
| テキスト出力         | Gemini **2.5 Pro**          | `gemini-2.5-pro`                                                                       | 安定版            | 高精度な推論・コーディング   | **5 RPM / 250k TPM / 100 RPD**               |
| テキスト出力         | Gemini **2.5 Flash**        | `gemini-2.5-flash`                                                                     | 安定版            | 価格性能バランス・低遅延    | **10 RPM / 250k TPM / 250 RPD**              |
| テキスト出力         | Gemini **2.5 Flash-Lite**   | `gemini-2.5-flash-lite`                                                                | 安定版            | 最小コスト・高スループット   | **15 RPM / 250k TPM / 1,000 RPD**            |
| テキスト出力         | Gemini **2.0 Flash**        | `gemini-2.0-flash`                                                                     | 安定版            | 1Mトークン文脈等の次世代機能 | **15 RPM / 1M TPM / 200 RPD**                |
| テキスト出力         | Gemini **2.0 Flash-Lite**   | `gemini-2.0-flash-lite`                                                                | 安定版            | 低コスト・低遅延        | **30 RPM / 1M TPM / 200 RPD**                |
| Live API       | **2.5 Flash Live**          | `gemini-live-2.5-flash-preview`                                                        | プレビュー          | 低遅延の音声/映像対話     | **同時3セッション / 1M TPM**（RPD記載なし）               |
| Live API（音声生成） | **2.5 Flash Native Audio**  | `gemini-2.5-flash-preview-native-audio-dialog` / `...exp-native-audio-thinking-dialog` | プレビュー/実験       | 高品質TTS対話        | **1セッション / 25k or 10k TPM / 5 RPD**          |
| TTS            | **2.5 Flash Preview TTS**   | `gemini-2.5-flash-preview-tts`                                                         | プレビュー          | 低遅延TTS          | **3 RPM / 10k TPM / 15 RPD**                 |
| 画像生成           | **2.0 Flash 画像生成（Preview）** | `gemini-2.0-flash-preview-image-generation`                                            | プレビュー          | 会話的画像生成/編集      | **10 RPM / 200k TPM / 100 RPD**              |
| 埋め込み           | **Gemini Embedding**        | `gemini-embedding-001` 等                                                               | 安定版            | 埋め込み生成          | **100 RPM / 30k TPM / 1,000 RPD**            |
| 軽量オープン         | **Gemma 3 / 3n**            | `gemma-3` 系                                                                            | 安定版            | 軽量推論            | **30 RPM / 15k TPM / 14,400 RPD**            |
| 旧世代            | **1.5 Flash/8B/Pro**        | `gemini-1.5-*`                                                                         | **Deprecated** | 2025/9 廃止予定     | 参考値：1.5 Flash=**15 RPM / 250k TPM / 50 RPD** |


RPM＝Requests per Minute：1分あたりのAPIリクエスト上限（プロジェクト単位）。 
Google AI for Developers

TPM＝Tokens per Minute (input)：1分あたりに“入力”として送れるトークン数の上限。 
Google AI for Developers

RPD＝Requests per Day：1日あたりのAPIリクエスト上限。太平洋時間の真夜中にリセット（日本時間では概ね夏時間=16:00、冬時間=17:00）。

