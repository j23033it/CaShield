---

### `TECHNOLOGIES.md`（全文）

```markdown
# 使用技術一覧（最新版）

本プロジェクトで利用している主要技術と使用箇所をまとめます。  
**実行フロー**：`sounddevice` → `WebRTC VAD` → `faster-whisper（二段: FAST/FINAL）` → `KWS（かな正規化 + 単純一致）` → 原文ログ → **Gemini 要約** → Web 表示（SSE）

---

## コアライブラリ

| ライブラリ/モジュール | 概要 | 主な使用ファイル |
|---|---|---|
| **faster-whisper** | Whisper を CTranslate2 バックエンドで高速実行（FAST/FINAL 二段） | `src/asr/dual_engine.py` |
| **CTranslate2** | 高速推論エンジン（faster-whisper のバックエンド） | 〃 |
| **sounddevice** | 低レイテンシ音声入力（RawInputStream） | `src/audio/sd_input.py`, `scripts/rt_stream.py` |
| **webrtcvad** | 音声区間検出（VAD）／無い場合はフォールバック | `src/vad/webrtc.py`, `scripts/rt_stream.py` |
| **pykakasi** | かな正規化（KWS 前処理）+ 単純一致 | `src/kws/simple.py` |
| **Flask** | Web API / テンプレート / SSE（ログの追記配信） | `webapp/app.py`, `webapp/templates/*` |
| **google-genai** | Gemini クライアント（構造化JSON生成） | `src/llm/client_gemini.py` |

> 備考：警告音再生は OS ネイティブ（Windows: winsound / macOS: afplay / Linux: ffplay/aplay）に統一し、`action_manager.py` で非ブロッキング再生します（.env 不使用・コード内設定）。

---

## 標準 / 周辺ライブラリ

| ライブラリ | 用途 | 主な使用ファイル |
|---|---|---|
| **threading** / **asyncio** | 録音スレッド / LLMワーカの非同期処理 | `scripts/rt_stream.py`, `scripts/llm_worker.py` |
| **time / datetime** | 計測・タイムスタンプ・アンカー時刻 | `scripts/rt_stream.py`, `src/llm/queue.py` |
| **os / pathlib** | ファイル・環境変数 | 全般 |
| **json** | JSONL入出力 | `src/llm/queue.py`, Web API |
| — | — | — |
| **numpy** | PCM16→float32 変換など | `src/asr/dual_engine.py`, VADフォールバック |

---

## モデル・推論設定の目安

- **CPU 環境**：`device=cpu` / `compute_type=int8`（既定）  
- **GPU（CUDA）**：`device=cuda` / `compute_type=float16` を推奨  
- **ASR 設定（コード内）**：`src/config/asr.py` に FAST/FINAL のモデル・ビーム・VAD 等を集約  
  - FAST = `small (int8, beam=2)` / FINAL = `large-v3 (int8, beam=5)`（既定）  
- **Gemini モデル**：`.env` は使用せず、`src/llm/client_gemini.py` の `self.model` に直接記述（例：`gemini-2.5-flash-lite`）

---

## I/O とプロトコル

- **音声**：16kHz / mono / PCM16（bytes）  
- **原文ログ**：LF区切りのプレーンテキスト（1行1発話）。`[NG: …]` マークを基点に LLM が窓取り  
- **要約**：JSONL（1 NG 事象 ≒ 1 行）。`{ ng_word, turns[], summary, severity(1–2), action, meta }`（severity は keywords.txt の既定値を採用）  
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

- **APIキーはコード内設定**で管理（`.env` は使用しません）。`src/llm/client_gemini.py` の `self.api_key` を設定してください。  
- 長期運用は **systemd**（Raspberry Pi）で `rt_stream` / `app.py` / `llm_worker` をそれぞれ常駐化

### Raspberry Pi ヘッドレス運用（HDMI 抜去対策）

- 端末切断・HDMI抜去に伴う `SIGHUP` によりプロセスが終了しないよう、各エントリースクリプトで `SIGHUP` を `SIG_IGN` に設定しています。
- 追加で `tmux`/`screen` の利用や `systemd` サービス化を推奨します。

---

## コード内設定

`.env` や環境変数は使用せず、以下のコード内で集中管理します。

- Gemini モデル名・温度など: `src/llm/client_gemini.py` の `self.model` / `self.temperature`
- LLMの出力最大トークンやリトライ等: `src/llm/client_gemini.py` の `LLMConfig` クラス
- ASR（FAST/FINAL）のモデル・ビーム・VAD: `src/config/asr.py` の `ASRConfig` クラス
- 要約ウィンドウ関連の閾値（秒数やトークン）: `src/llm/queue.py` 内の定数・既定値


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

