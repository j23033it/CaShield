# カスハラ対策AI － 置くだけ Pi

Raspberry Pi と USB マイクをレジ周辺に「置くだけ」で、理不尽な暴言（カスタマーハラスメント）を検知し、即座に警告音でけん制する小規模向け OSS プロジェクトです。

## 目的

- **ストレス軽減**: 現場で「とりあえず謝る」以外の選択肢を持ち、精神的負担を下げる
- **その場で抑止**: 暴言を可視化・可聴化して早期沈静化を促す
- **事後対応に備える**: ログを保存し、クレーム分析や再発防止策に活用できる土台を作る

## 前提条件

| 項目 | 必須 / 推奨 | 備考 |
|---|---|---|
| 本体 | Raspberry Pi 4 (4 GB RAM 以上推奨) | Raspberry Pi OS 64-bit |
| マイク | USB コンデンサマイク | 無指向性 / 16 kHz 以上推奨 |
| スピーカー | USB/Bluetooth スピーカー or GPIO ブザー | 警告音用 |
| ソフトウェア | Python 3.11+ | `requirements.txt` 参照 |

> 運用イメージ
> - Pi はレジ付近に常設し、プログラムを自動起動（systemd）で 24 h 動かす
> - 初回セットアップのみ HDMI モニタ＋キーボードをつないで CLI から起動・設定

## 機能（MVP）

- 音声の常時キャプチャ（16 kHz / mono / PCM16）
- 文字起こし: faster-whisper（CTranslate2 バックエンド、CPU int8 量子化）
- キーワード検知: ひらがな化したテキストと `config/keywords.txt` のワードで部分一致判定
- アクション: 警告音再生 + テキストログ出力

## ディレクトリ構成

```
src/
  audio/sd_input.py      # sounddevice による入力（RT）
  asr/engine.py          # faster-whisper ラッパ
  kws/simple.py          # 簡易 KWS（ひらがな化して部分一致）
  vad/webrtc.py          # WebRTC VAD による発話区間抽出
  action_manager.py      # 警告音再生・ログ
  audio_capture.py       # PyAudio 実装（簡易版）
  config.py, models.py, status_manager.py, transcriber.py, transcription.py
scripts/
  rt_stream.py           # リアルタイム監視（RT 構成）
assets/alert.wav         # 警告音
config/keywords.txt      # NG ワード
```

## インストール（Raspberry Pi）

```bash
sudo apt update
sudo apt install -y \
  python3-venv python3-dev build-essential \
  portaudio19-dev libatlas-base-dev \
  libsndfile1 ffmpeg

cd ~
git clone <YOUR_REPO_URL> CaShield_speed
cd CaShield_speed

python3 -m venv venv
source venv/bin/activate

pip install -U pip setuptools wheel
pip install -r requirements.txt
```

## 使い方

- シンプル実行（`main.py`）
  ```bash
  source venv/bin/activate
  python main.py
  ```

- リアルタイム実行（VAD + faster-whisper ストリーム）
  ```bash
  source venv/bin/activate
  python scripts/rt_stream.py
  ```

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

## 性能のヒント

- CPU なら `compute_type=int8` が高速（既定）
- GPU（CUDA）があれば `DEVICE=cuda`, `COMPUTE=float16`
- ビーム幅 `beam_size` を 1–2 にすると更に高速（精度とトレードオフ）

## 今後のバージョンでの実装予定

- 音声認識精度の向上
- db閾値等の判別方法の追加
- LLMを活用した会話ログをもとにした要約ログ作成
- フロントエンドの作成とそれに伴うバックエンドの機能追加（取得した会話ログをLLMに渡す処理など）

## 参考

- 構成の参考: [`j23033it/CaShield`](https://github.com/j23033it/CaShield.git)


