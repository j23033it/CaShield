---

### `TECHNOLOGIES.md`（全文）

```markdown
# 使用技術一覧（最新版）

本プロジェクトで利用している主要技術と使用箇所をまとめます。  
**実行フロー**：`sounddevice` → `WebRTC VAD` → `faster-whisper` → `KWS（ひらがな化によるキーワード検出）` → 原文ログ → **Gemini 要約** → Web 表示（SSE）

---

## コアライブラリ

| ライブラリ/モジュール | 概要 | 主な使用ファイル |
|---|---|---|
| **faster-whisper** | Whisper を CTranslate2 バックエンドで高速実行 | `src/asr/engine.py`, `src/transcription.py` |
| **CTranslate2** | 高速推論エンジン（faster-whisper のバックエンド） | 〃 |
| **sounddevice** | 低レイテンシ音声入力（RawInputStream） | `src/audio/sd_input.py`, `scripts/rt_stream.py` |
| **webrtcvad** | 音声区間検出（VAD）／無い場合はフォールバック | `src/vad/webrtc.py`, `scripts/rt_stream.py` |
| **pykakasi** | 認識テキストの**ひらがな変換**（KWS 前処理） | `src/kws/simple.py` |
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
| **yaml** | 任意の追加設定ファイル読込 | `scripts/rt_stream.py` |
| **numpy** | PCM16→float32 変換など | `src/transcription.py`, VADフォールバック |

---

## モデル・推論設定の目安

- **CPU 環境**：`device=cpu` / `compute_type=int8`（既定）  
- **GPU（CUDA）**：`device=cuda` / `compute_type=float16` を推奨  
- **Whisper モデル**：`tiny/base/small/...` は `src/config.py` から（RTは `scripts/rt_stream.py` の読み込み設定に依存）  
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




