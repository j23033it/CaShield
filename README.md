# CaShield - リアルタイム音声解析による対人業務支援AI

レジや窓口に置いたマイクからの音声を**リアルタイムで解析**し、暴言などの**NGワード**を検知すると、警告音やログ記録、LLMによる自動要約を行うことで、従業員の精神的負担を軽減し、事後対応を効率化することを目的としたシステムです。

## 主な機能

- **リアルタイム音声認識**: 低遅延の音声入力(VAD)と高速な文字起こし(faster-whisper)を実現。
- **NGワード検出**: 設定ファイルに基づき、会話内容からNGワードを検出します。
- **自動アクション**: NGワード検出時に、警告音を鳴らしてその場でのエスカレーションを抑止し、会話ログを自動で記録します。
- **LLMによる自動要約**: Gemini APIを利用し、インシデント発生時の会話を「要約」「深刻度」「推奨対応」を含む構造化データとして記録します。
- **Webインターフェース**: 記録された生ログと要約ログを、ブラウザから簡単に確認できます。

---

## ディレクトリ構成

本プロジェクトのロジックは、役割に応じて3つの主要なPythonファイルに統合されています。

```
.
├── backend.py            # 音声処理、文字起こしなどリアルタイム処理のコアロジック
├── llm.py                # LLM連携（要約生成）のコアロジック
├── frontend.py           # Web UI (Flask) のサーバーロジック
├── templates/            # WebページのHTMLテンプレート
├── static/               # CSS, JS, 画像ファイル
├── assets/               # 警告音などのリソースファイル
├── config/               # NGワードリストなどの設定ファイル
├── logs/                 # 生成された会話ログと要約ログ
├── venv/                 # Python仮想環境
├── .gitignore
├── README.md             # このファイル
└── requirements.txt      # 依存パッケージリスト
```

---

## セットアップ

### 1. リポジトリのクローン
```bash
git clone https://github.com/j23033it/CaShield.git
cd CaShield
```

### 2. Python仮想環境の構築と有効化
```bash
# Windows
python -m venv venv
.\venv\Scripts\Activate.ps1

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. 依存パッケージのインストール
```bash
pip install -U pip
pip install -r requirements.txt
```

### 4. APIキーの設定
`llm.py` ファイルを直接編集し、ご自身のGemini APIキーを設定してください。

```python
# llm.py の編集箇所
class GeminiSummarizer:
    def __init__(self, cfg: Optional[LLMConfig] = None) -> None:
        self.api_key: str = "YOUR_API_KEY_HERE"  # ← ここにAPIキーを設定
        # ...
```

---

## 実行方法

本システムは、**3つのプロセスを個別のターミナルで同時に実行する**必要があります。
プログラムは必ず、**リポジトリのルートディレクトリ**から実行してください。

#### 1. バックエンド起動 (リアルタイム監視)
音声の監視、文字起こし、NGワード検出、ログ記録を行います。

```bash
python backend.py
```

#### 2. LLMワーカー起動
ログファイルを監視し、NGワードが記録されるとLLMによる要約を生成します。

```bash
python llm.py
```

#### 3. フロントエンド起動 (Web UIサーバー)
ログを閲覧するためのWebサーバーを起動します。

```bash
python frontend.py
```

起動後、ブラウザで `http://127.0.0.1:5000` にアクセスしてください。