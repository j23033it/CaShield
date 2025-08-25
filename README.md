# カスハラ対策AI － 置くだけ Pi

レジ付近に置いたマイク音声を**リアルタイム監視**し、暴言などの **NGワード** を検知すると、以下の処理を自動的に行います。

- **警告音の再生**: その場での抑止効果を狙います。
- **原文ログの記録**: `logs/YYYY-MM-DD.txt` に、NGワードをマークして会話を記録します (`[NG: …]` のように表示)。
- **AIによる要約**: **Gemini** を利用して会話を要約し、`logs/summaries/<date>.jsonl` に保存します。
- **Web UIでの閲覧**: 要約をカード形式で (`/summaries/<date>`)、原文をテキストで (`/logs/<date>`) 確認できます。

## 目的

- **ストレス軽減**: 現場担当者が「とりあえず謝る」以外の選択肢を持つことで、精神的負担を軽減します。
- **その場で抑止**: 暴言を即座に可視化・可聴化し、状況の早期沈静化を促します。
- **事後対応の効率化**: ログと要約を活用し、クレーム分析や再発防止策の検討をサポートします。

## 主な機能

- **低レイテンシ音声入力**: `sounddevice` を使用 (16kHz, モノラル, PCM16)。
- **音声認識 (ASR)**: `faster-whisper` (CTranslate2) をCPU (int8) で高速に実行。
- **キーワード検出 (KWS)**: 認識テキストをかな正規化し、rapidfuzz の部分一致で NG ワードを検出。
- **VAD (音声区間検出)**: `webrtc-vad` を使用し、無音区間をカット。
- **警告音再生**: `assets/alert.wav` を再生。
- **ログ記録**: `logs/YYYY-MM-DD.txt` に原文を追記。
- **LLMによる要約**: `Gemini` を利用して、インシデントをJSONL形式で要約。
- **Web UI (Flask)**:
  - `/logs/<date>`: 原文ログをリアルタイム表示 (Server-Sent Events)。
  - `/summaries/<date>`: 要約カード (深刻度、推奨対応、該当箇所など) を表示。

---

## セットアップ

### 前提条件

- **Python**: 3.11 以上
- **Gemini API キー**: `.env` ファイルまたは環境変数 (`GEMINI_API_KEY` or `GOOGLE_API_KEY`) に設定。
- **マイク**: USBマイク (無指向性推奨)。
- **FFmpeg**: 音声の前処理に必要です。
  - **Raspberry Pi**: `sudo apt install ffmpeg`
  - **Windows**:別途インストールが必要です。

> [!IMPORTANT]
> プログラムの実行は、必ずリポジトリのルートディレクトリで `python -m <module_name>` の形式で行ってください。

### .env ファイルの作成

リポジトリのルートに `.env` ファイルを作成します (このファイルはGitの管理対象外です)。

```dotenv
# .env
GEMINI_API_KEY="<あなたのAPIキー>"
CASHIELD_GEMINI_MODEL="gemini-1.5-flash-latest"
CASHIELD_LLM_TEMP=0.1
```

---

## インストール & 起動 (Raspberry Pi)

### 1. 依存ライブラリのインストール

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential \
  portaudio19-dev libatlas-base-dev libsndfile1 ffmpeg
```

### 2. リポジトリのクローン

```bash
git clone https://github.com/j23033it/CaShield.git
cd CaShield
```

### 3. Python仮想環境の構築と有効化

```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Pythonパッケージのインストール

```bash
pip install -U pip setuptools wheel
pip install -r requirements.txt
```

### 5. `.env` ファイルの作成

エディタで `.env` ファイルを開き、APIキーを設定します。

```bash
nano .env
```

---

## 使い方

### リアルタイム監視

```bash
# VAD -> ASR -> KWS -> ログ書き出し
python -m scripts.rt_stream
```

### LLM要約ワーカー

```bash
# ログを監視し、新しいインシデントを要約
python -m scripts.llm_worker
```

### Web UIの起動

```bash
# /logs と /summaries を提供
python -m webapp.app
```

> [!NOTE]
> **運用イメージ**:
> - Raspberry Piをレジ付近に常設し、`systemd` などでプログラムを自動起動させ、24時間稼働させます。
> - 初回セットアップ時のみ、モニターとキーボードを接続して設定を行います。

---

## ディレクトリ構成

```
.
├── assets/
│   └── alert.wav
├── config/
│   └── keywords.txt
├── logs/
│   ├── YYYY-MM-DD.txt
│   └── summaries/
│       └── <date>.jsonl
├── scripts/
│   ├── rt_stream.py          # リアルタイム監視
│   ├── llm_worker.py         # LLM要約ワーカー
│   └── create_alert_sound.py # 警告音生成
├── src/
│   ├── asr/dual_engine.py    # 二段ASR（FAST/FINAL）
│   ├── audio/sd_input.py     # 低レイテンシ音声入力
│   ├── kws/simple.py         # キーワード検出
│   ├── llm/client_gemini.py  # Geminiクライアント
│   ├── vad/webrtc.py         # VAD
│   └── ...
├── webapp/
│   ├── app.py                # Flask Webサーバー
│   ├── static/               # 画像・音声ファイル
│   └── templates/            # HTMLテンプレート
├── .env                      # (作成する) APIキー（ASR設定はコード内に集約）
├── main.py
├── requirements.txt
└── README.md
```

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

## 今後のバージョンでの実装予定

- 音声認識精度の向上
- db閾値等の判別方法の追加
- LLMを活用した会話ログをもとにした要約ログ作成と品質向上
- フロントエンドの作成とそれに伴うバックエンドの機能追加（取得した会話ログをLLMに渡す処理など）

## 参考

- 構成の参考: [`j23033it/CaShield`](https://github.com/j23033it/CaShield.git)


