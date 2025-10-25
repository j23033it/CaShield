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
- **キーワード検出 (KWS)**: 認識テキストをかな正規化し、rapidfuzz の部分一致スコアで NG を判定（既定しきい値は保守的に高め）。
  - 誤検知抑制のため、短すぎる語は無視（最小長設定）。
  - 警告音は ASR 結果が NG ワードを含む場合に即座に鳴動。
  - 既知のハルシネーション（例: 「ご視聴ありがとうございました」「ありがとうございました」等）はコード内フィルタで除外。
- **VAD (音声区間検出)**: `webrtc-vad` を使用し、無音区間をカット。
- **警告音再生**: `assets/alert.wav` を再生（OSネイティブ: Windows=winsound, macOS=afplay, Linux=ffplay/aplay）。非ブロッキング・設定はコード内。
- **ログ記録**: `logs/YYYY-MM-DD.txt` に原文を追記。
- **LLMによる要約**: `Gemini` を利用して、インシデントをJSONL形式で要約。
- **Web UI (Flask)**:
  - `/logs/<date>`: 原文ログをリアルタイム表示 (Server-Sent Events)。
  - `/summaries/<date>`: 要約カード (深刻度、推奨対応、該当箇所など) を表示。

---

## セットアップ

### 前提条件

- **Python**: 3.11 以上
- **Gemini API キー**: コード内設定に直接記述します（.envは使用しません）。
  - 設定ファイル: `src/llm/client_gemini.py`
  - 変数: `GeminiSummarizer.__init__` 内の `self.api_key` を編集してください。
- **マイク**: USBマイク (無指向性推奨)。
- **FFmpeg**: 音声の前処理に必要です。
  - **Raspberry Pi**: `sudo apt install ffmpeg`
  - **Windows**:別途インストールが必要です。

> [!IMPORTANT]
> プログラムの実行は、必ずリポジトリのルートディレクトリで `python -m <module_name>` の形式で行ってください。

### APIキーの設定（コード内設定）

エディタで `src/llm/client_gemini.py` を開き、`self.api_key` にAPIキーを設定してください。

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

### 5. APIキーの設定（コード内設定）

エディタで `src/llm/client_gemini.py` を開き、`self.api_key` にAPIキーを設定します。

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

---

## キーワードと深刻度（severity）の扱い（重要）

- キーワード定義ファイル: `config/keywords.txt`
- 対応フォーマット：
  - レベル行形式（推奨・複数行対応）
    - 例: `level1=[黙れ, いい加減にしろ,\n            地獄に落ちろ]`, `level2=[殺す, 死ね]`
    - `level<数値>` が深刻度（整数）。`[]` 内は改行・末尾カンマ可。
  - 1行1語形式（後方互換）
    - 深刻度は既定で `2` として扱います（2段階制）。
- 深刻度は LLM の出力ではなく、上記ファイルで定義された既定値を採用して保存します。
- 画面表示では、要約カードの「深刻度」がこの既定値（1〜2）に基づいて表示されます。

## ハルシネーションの除外

- 集中管理: `src/config/filter.py`
- 除外対象: 「ご視聴ありがとうございました」「ありがとうございました」など、締めの定型文（完全一致）
- 適用箇所:
  - `scripts/rt_stream.py` の ASR 結果（ログ追記前に除外）
  - `webapp/app.py` の `parse_log_line`（保険として表示前に除外）

> [!NOTE]
> **運用イメージ**:
> - Raspberry Piをレジ付近に常設し、`systemd` などでプログラムを自動起動させ、24時間稼働させます。
> - 初回セットアップ時のみ、モニターとキーボードを接続して設定を行います。

## Raspberry Pi ヘッドレス運用（HDMI抜去時の強制終了対策）

- 背景: Raspberry Pi を HDMI 接続したまま実行し、後から HDMI ケーブルを抜くと、セッション切断に伴う `SIGHUP` がプロセスへ送られ、強制終了することがあります。
- 対策: 本プロジェクトでは以下のエントリースクリプトで `SIGHUP` を無視する初期化を入れ、ヘッドレス運用でも終了しないようにしています。
  - `scripts/rt_stream.py` … `main()` 冒頭で `signal.signal(signal.SIGHUP, signal.SIG_IGN)`
  - `scripts/llm_worker.py` … `amain()` 冒頭で同様
  - `webapp/app.py` … `__main__` ブロックで同様
- 追加の耐障害化: `scripts/rt_stream.py` のメインループは、音声入出力/ASR/VAD 由来の実行時例外を握り、
  入力ストリームを自動再初期化して処理を継続します（短時間のリトライを含む）。
- 併用推奨:
  - `tmux`/`screen` 上で各プロセスを起動（端末切断の影響を受けない）
  - `systemd` 常駐化（自動起動・自動再起動・ログ集約）

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
│   ├── asr/single_engine.py  # 単一段ASRエンジン
│   ├── audio/sd_input.py     # 低レイテンシ音声入力
│   ├── kws/simple.py         # キーワード検出
│   ├── llm/client_gemini.py  # Geminiクライアント
│   ├── vad/webrtc.py         # VAD
│   └── ...
├── webapp/
│   ├── app.py                # Flask Webサーバー
│   ├── static/               # 画像・音声ファイル
│   └── templates/            # HTMLテンプレート
├── docs/
│   ├── TECHNOLOGIES.md
│   ├── QUESTIONS.md
│   ├── EXPLAN.md
│   └── ALERT.md
├── AGENTS.md
├── （APIキーはコード内設定: src/llm/client_gemini.py）
├── main.py
├── requirements.txt
└── README.md
```

### ディレクトリの役割（抜粋）

- `src/models.py`: データモデル定義。
  - `AudioData`: 録音バイト列とサンプリング情報を保持（長さ計算などの補助を提供）。
  - `TranscriptionResult`: ASR 結果（本文、信頼度、セグメント、メタ）を表現。
  - `AppConfig`: アプリ全体設定（モデル名や言語などの簡易表現）。

- `src/llm/`
  - `client_gemini.py`: Gemini クライアント。`GeminiSummarizer` と `LLMConfig` を提供。
    - APIキー・モデル名・温度・max tokens・リトライは「コード内設定」（.env は不使用）。
    - 出力 JSON のスキーマを定義。`severity` は任意（保存時は keywords の既定値を採用）。
  - `windowing.py`: LLM に渡す会話窓の構築ロジック。
    - `Turn`/`Snippet` モデル、`parse_line()`、`build_window()`（`min_sec`/`max_sec`/`max_tokens`を満たすよう拡張）。
  - `queue.py`: LLM 要約ジョブの実行と保存。
    - `Job` と `WindowConfig`、`LLMJobRunner` を提供。窓取り→要約→`logs/summaries/<date>.jsonl` へ1行追記。エラーは `*.errors.log` に保存。

- `docs/`
  - `TECHNOLOGIES.md`: 採用技術の一覧と利用箇所、推奨モデル設定などの補足情報。
  - `QUESTIONS.md`: 発表・デモ向けのQ&Aカンペ。レイテンシやNGワード運用の要点を整理。
  - `EXPLAN.md`: 詳細なディレクトリ構成、データフロー、各ファイルの責務をまとめたリファレンス。
  - `ALERT.md`: 警告音・通知音・入力デバイス・ログ命名など運用時に変更しやすい項目の設定手順。
- `AGENTS.md`: 開発支援AIが守るべき方針やドキュメント編集ルール、逐次コミットの義務などを示したガイドライン。

### 起動（3プロセス／別ターミナル or tmux）

# A: RT監視（VAD→ASR→KWS→logs/<date>.txt 追記）
python -m scripts.rt_stream
# B: Web（http://0.0.0.0:5000）
python -m webapp.app
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

### APIキーの設定（コード内設定）
メモ帳で `src\llm\client_gemini.py` を開き、`self.api_key` に API キーを設定してください。

### 起動（3プロセス）
# A: RT監視（必ずリポジトリのルートで -m 実行）
python -m scripts.rt_stream
# B: Web（http://127.0.0.1:5000）
python -m webapp.app
# C: LLMワーカー
python -m scripts.llm_worker

## 今後のバージョンでの実装予定

- 音声認識精度の向上
- db閾値等の判別方法の追加
- LLMを活用した会話ログをもとにした要約ログ作成と品質向上
- フロントエンドの作成とそれに伴うバックエンドの機能追加（取得した会話ログをLLMに渡す処理など）

## 参考

- 構成の参考: [`j23033it/CaShield`](https://github.com/j23033it/CaShield.git)


