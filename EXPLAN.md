### プロジェクト構成と各ファイルの役割

このドキュメントは、最新のディレクトリ構成と各ファイルの役割を簡潔に説明します。

## 全体構成（要約）

```
src/
  audio/sd_input.py      # 低レイテンシ音声入力（sounddevice）
  asr/dual_engine.py     # faster-whisper 二段ラッパ（FAST/FINAL）
  kws/fuzzy.py           # かな正規化 + rapidfuzz の KWS
  kws/keywords.py        # keywords.txt の読み込みと深刻度マップ
  vad/webrtc.py          # WebRTC VAD による発話区間抽出
  action_manager.py      # 警告音・ログ処理（非ブロッキング）
  config/asr.py          # ASR 設定（コード内に集約: FAST/FINAL, VAD など）
  config/filter.py       # ハルシネーション除外設定
  llm/client_gemini.py   # Gemini クライアント（コード内設定）
  llm/windowing.py       # LLM要約用の窓取りロジック
  llm/queue.py           # LLM要約ジョブ実行/保存
scripts/
  rt_stream.py           # リアルタイム監視のエントリ（VAD→ASR→KWS→アクション）
  create_alert_sound.py  # 簡易な警告音ファイル生成スクリプト
  llm_worker.py          # ログ監視とLLM要約ワーカ
  purge_raw_logs.py      # TTL経過の原文行を要約採用分のみ残す
webapp/
  app.py                 # Flask Webサーバ
  templates/             # HTMLテンプレート
  static/                # 画像・音声ファイル
assets/alert.wav         # 警告音のデフォルトファイル
config/keywords.txt      # NGワード一覧（レベル行形式/1行1語）
logs/                    # 検出ログの出力
README.md, TECHNOLOGIES.md, explan.md, requirements.txt
```

## ディレクトリの役割

- `src/`
  - アプリ本体のコードを集約するルートパッケージ。
  - `audio/`
    - `sd_input.py`: sounddevice の `RawInputStream` による低レイテンシ入力。リングバッファで 20–30 ms 単位のチャンク化。
  - `asr/`
    - `dual_engine.py`: `faster-whisper` を使った二段ラッパ（FAST→FINAL）。PCM16→float32 変換、非同期FINAL実行。
  - `kws/`
    - `simple.py`: 認識テキストをひらがな化し、`keywords.txt` の各語と部分一致で照合。
    - `keywords.py`: `keywords.txt` を解析し、キーワード一覧と深刻度マップを返す（レベル記法は複数行対応、2段階制）。
  - `llm/`
    - `client_gemini.py`: Gemini クライアント。`GeminiSummarizer` と `LLMConfig` を提供し、コード内設定（APIキー・モデル名・温度・最大トークン・リトライ）で構成。要約のJSONスキーマを定義し、severity は任意（保存時は keywords の既定値を採用）。
    - `windowing.py`: LLMに渡す会話窓の構築。`Turn`/`Snippet` モデル、`parse_line()`、`build_window()`（min_sec / max_sec / max_tokens を満たすように前後を拡張し anchor_time を算出）。
    - `queue.py`: LLM要約ジョブ実行。`Job` と `WindowConfig`、`LLMJobRunner` を提供。窓取り→Gemini要約→`logs/summaries/<date>.jsonl` への1行JSON追記、エラーは `*.errors.log` に記録。
  - `config/`
    - `filter.py`: 既知ハルシネーション（定型文）の除外設定と判定関数
  - `vad/`
    - `webrtc.py`: WebRTC VAD を使った発話区間抽出器。前後パディングや短ポーズ連結を実装。
  - ルート直下
    - `action_manager.py`: 検出時の警告音再生・ログを非ブロッキングに実行。
    - `models.py`: データモデル定義。`AudioData`（録音データとメタ）/ `TranscriptionResult`（ASR結果・スコア・メタ）/ `AppConfig`（アプリ設定の簡易表現）。

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

3. **ASR**（`src/asr/dual_engine.py`）  
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
   - 原文ログを監視し、NG行を基点に**窓取り**（min_sec≥12 / max_sec≤30 / tokens≤512）  
   - **構造化JSON**を生成：`{ ng_word, turns[], summary, severity(1–2), action }`（severity は keywords.txt の既定値を採用）
   - `logs/summaries/<date>.jsonl` に**1 NG 事象＝1行**で追記  
   - 失敗は `logs/summaries/<date>.errors.log` と `logs/summaries/errors/*.log` に保存

7. **Web表示**（`webapp/app.py`）  
   - `/` … 日付一覧  
   - `/logs/<date>` … 原文表示（初回ロードで全件表示し、SSE `/stream/<date>` で追記。追記時に通知音）  
   - `/api/logs/<date>` … 原文のJSON配列  
   - `/summaries/<date>` … 要約カード表示（深刻度は 1〜3 で表示）

---

## 運用（Raspberry Pi ヘッドレス / HDMI 抜去対策）

- 背景: HDMI を抜去すると、セッション切断由来の `SIGHUP` がプロセスへ送られ終了することがある。
- 実装: エントリースクリプトで `SIGHUP` を無視。
  - `scripts/rt_stream.py` → `main()` で `signal.SIGHUP` を `SIG_IGN`
  - `scripts/llm_worker.py` → `amain()` で同様
  - `webapp/app.py` → `__main__` で同様
- 推奨: `tmux`/`screen` での起動、もしくは `systemd` で常駐化。

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
  "severity": 2,
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
  

## 実行の最短手順（再掲）

```bash
source venv/bin/activate
# リアルタイム監視（推奨）
python -m scripts.rt_stream
# LLM要約ワーカー（別ターミナル）
python -m scripts.llm_worker
```


