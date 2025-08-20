# カスハラ対策AI － 置くだけ Pi

レジ付近に置いたマイク音声を**リアルタイム監視**し、暴言などの **NGワード** を検知したら  
- 警告音を鳴らす（その場の抑止）  
- `logs/YYYY-MM-DD.txt` に**原文ログ**を追記（`[NG: …]` マーク付）  
- **Gemini** で要約し `logs/summaries/<date>.jsonl` へ保存  
- Web で **要約カード**（/summaries/<date>）と **原文**（/logs/<date>）を閲覧を行うソフトウェア

## 目的

- **ストレス軽減**：現場で“とりあえず謝る”以外の選択肢を持ち、精神的負担を下げる  
- **その場で抑止**：暴言を可視化・可聴化して早期沈静化を促す  
- **事後対応**：ログと要約を残し、クレーム分析や再発防止検討の材料にする 

## 前提条件

- **Python**：3.11 以上推奨  
- **Gemini API キー**：`.env` または OS 環境変数（`GEMINI_API_KEY` または `GOOGLE_API_KEY`）  
- **マイク**：USB マイク（無指向性推奨）  
- **FFmpeg**：ASR 前処理で使用（Pi は `apt install ffmpeg`、Windows は別途導入可）

> 実行は **リポジトリのルート**で **`python -m`** 形式に統一してください。

> Web UI は Flask を使用。フロントは Server-Sent Events（SSE）でログを**追記表示**します。


> 運用イメージ
> - Pi はレジ付近に常設し、プログラムを自動起動（systemd）で 24 h 動かす
> - 初回セットアップのみ HDMI モニタ＋キーボードをつないで CLI から起動・設定

## 機能（MVP）

- **低レイテンシ音声入力**（sounddevice / 16kHz mono, PCM16）
- **警告音再生**（assets/alert.wav）
- **音声認識**：faster-whisper（CTranslate2 / CPU int8 既定）
- **KWS**：認識テキストを**ひらがな化**し `config/keywords.txt` と部分一致
- **ログ**：`logs/YYYY-MM-DD.txt` に原文追記（[NG: …] マークあり）
- **要約**：`logs/summaries/<date>.jsonl` に LLM 要約（JSONL）
- **Web UI**：  
  - `/logs/<date>` … 原文（緊急参照用／SSEでリアルタイム追記）  
  - `/summaries/<date>` … **要約カード**（深刻度/対応/該当区間メタ）

## ディレクトリ構成

src/
audio/sd_input.py # 低レイテンシ入力
asr/engine.py # faster-whisper ラッパ
kws/simple.py # ひらがなKWS
vad/webrtc.py # WebRTC VAD（フォールバック内蔵）
llm/
client_gemini.py # Gemini クライアント（.env対応 / JSON構造化）
queue.py # 要約ジョブ実行・JSONL保存
windowing.py # 窓取りロジック
action_manager.py # 警告音・（必要に応じ）ログ
config.py / models.py / status_manager.py / transcription.py ...
scripts/
rt_stream.py # RT監視（VAD→ASR→KWS→ログ書き出し）
llm_worker.py # LLMワーカー（JSONL要約生成）
create_alert_sound.py # 警告音生成
webapp/
app.py # Flask Web（/logs /summaries API含む）
templates/ # index.html / log.html
static/ # 画像と通知音（customer.png / clerk.png / notify.mp3）
assets/alert.wav
config/keywords.txt
logs/ # 生成先（原文 .txt / 要約 .jsonl / エラー .log）


## セットアップ（共通: .env）

`.env` は **コミット禁止**。リポジトリ直下に作成します。
GEMINI_API_KEY=＜あなたのキー＞ # または GOOGLE_API_KEY=＜あなたのキー＞
CASHIELD_GEMINI_MODEL=gemini-2.5-flash-lite
CASHIELD_LLM_TEMP=0.1



## インストール & 起動（Raspberry Pi）

### 依存ライブラリ
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential \
  portaudio19-dev libatlas-base-dev libsndfile1 ffmpeg

### 取得
git clone https://github.com/j23033it/CaShield.git
cd CaShield_speed

### 仮想環境 & Python 依存

python3 -m venv venv
source venv/bin/activate

pip install -U pip setuptools wheel
pip install -r requirements.txt

### .env 作成

nano .env

### 起動（3プロセス／別ターミナル or tmux）

# A: RT監視（VAD→ASR→KWS→logs/<date>.txt 追記）
python -m scripts.rt_stream
# B: Web（http://0.0.0.0:5000）
python webapp/app.py
# C: LLMワーカー（logs/summaries/<date>.jsonl を生成）
python -m scripts.llm_worker


## インストール & 起動（Windows 10/11・PowerShell）

### 取得
git clone https://github.com/j23033it/CaShield.git
cd .\CaShield

### 仮想環境&依存
python -m venv venv
.\venv\Scripts\Activate.ps1

pip install -U pip setuptools wheel
pip install -r requirements.txt

### .env 作成
notepad .\.env

### 起動（3プロセス）
# A: RT監視（必ずリポジトリのルートで -m 実行）
python -m scripts.rt_stream
# B: Web（http://127.0.0.1:5000）
python .\webapp\app.py
# C: LLMワーカー
python -m scripts.llm_worker




## 設定

- キーワード: `config/keywords.txt`
- 追加の設定（任意）: `config/config.yaml`（存在すれば読み込み）
  - 例:
    ```yaml
    sample_rate: 16000
    block_ms: 30
    vad:
      aggressiveness: 2
      pad_prev_ms: 200
      pad_post_ms: 300
    asr:
      model: small
      device: cpu           # cuda があれば cuda
      compute_type: int8    # CPU: int8 / GPU: float16
      beam_size: 3
      initial_prompt_path: null
    ```
- 環境変数で上書き（`scripts/rt_stream.py`）
  - `CASHIELD_MODEL`, `CASHIELD_DEVICE`, `CASHIELD_COMPUTE`, `CASHIELD_BEAM`, `CASHIELD_BLOCK_MS`, `CASHIELD_VAD_AGGR`, `CASHIELD_INPUT_DEVICE`


## 今後のバージョンでの実装予定

- 音声認識精度の向上
- db閾値等の判別方法の追加
- LLMを活用した会話ログをもとにした要約ログ作成
- フロントエンドの作成とそれに伴うバックエンドの機能追加（取得した会話ログをLLMに渡す処理など）

## 参考

- 構成の参考: [`j23033it/CaShield`](https://github.com/j23033it/CaShield.git)


