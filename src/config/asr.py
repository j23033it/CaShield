class ASRConfig:
    """
    単一段 ASR 用のコード内設定クラス。

    - .env は使用せず、本クラスのクラス属性（定数）で全て管理します。
    - 参照箇所:
      - `src/asr/single_engine.py`（モデル読み込み・推論パラメータ）
      - `scripts/rt_stream.py`（ストリーミング入出力、VAD、KWS）

    設定の考え方:
    - 単一モデルで即時性と精度を両立させ、ビーム幅などのパラメータを調整します。
    - CPU 前提では `compute_type=int8` が高速・省メモリ。GPU(CUDA)なら `float16` を推奨。
    - 本番環境で変更したいのは主にモデル名・ビーム幅・デバイス種別です。
    """

    # --- ASR 推論設定 ---
    # 使用モデル名（faster-whisper のモデル識別子）
    MODEL_NAME = "base"
    # 推論の計算精度（CPU: int8/int8_float16、GPU: float16 など）
    COMPUTE_TYPE = "int8"
    # ビームサーチ幅（大きいほど精度は上がるが遅くなる）
    BEAM_SIZE = 4

    # --- 共通 ASR パラメータ ---
    # 推論デバイス（"cpu" / "cuda"）
    DEVICE = "cpu"
    # 認識言語（日本語固定）
    LANGUAGE = "ja"
    # サンプリングの温度（低いほど決定的。ASRでは通常 0）
    TEMPERATURE = 0.0
    # 低確率（平均対数尤度）の打ち切り閾値（Whisperの no/low speech 判定向け）
    LOG_PROB_THRESHOLD = -0.8
    # 無音判定のしきい値（大きいほど無音と判定しやすい）
    NO_SPEECH_THRESHOLD = 0.6
    # VAD フィルタ使用可否（入力はVAD済みだが、保険として有効にできる）
    VAD_FILTER = True

    # --- ストリーミング / VAD 前段 ---
    # オーディオのサンプルレート（Whisper は 16kHz が標準）
    SAMPLE_RATE = 16000
    # 入力フレーム長（ミリ秒）。20〜30ms 程度が一般的
    # 語尾/語頭の取りこぼしを減らす目的で分解能を上げる（30→20ms）
    BLOCK_MS = 20
    # WebRTC VAD の攻撃性（0〜3：大きいほど“非音声”に厳しい）
    # 切り過ぎを抑えるため 2→1 に緩和
    VAD_AGGRESSIVENESS = 1
    # 発話検出時に前後へ付与するパディング（ミリ秒）
    # 文頭/文末の欠落を抑える（200→240ms / 300→500ms）
    PAD_PREV_MS = 240
    PAD_POST_MS = 500

    # --- KWS（キーワード検出） ---
    # かな正規化 + 類似度ベース（rapidfuzz.partial_ratio）で検出。
    # 誤検知/ハルシネーション抑制のため、しきい値は保守的に高め（例: 90）。
    KWS_FUZZY_THRESHOLD = 90
    # 短すぎるキーワードは誤検知の温床になるため、かな長がこの値未満は無視。
    KWS_MIN_HIRA_LEN = 2

    # --- ASR 初期プロンプト（任意） ---
    # スタイル/固有名詞の事前ヒントなどを与えたい場合のテキストパス
    INITIAL_PROMPT_PATH = None
