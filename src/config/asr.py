class ASRConfig:
    """
    二段ASR（FAST/FINAL）用のコード内設定クラス。

    - .env は使用せず、本クラスのクラス属性（定数）で全て管理します。
    - 参照箇所:
      - `src/asr/dual_engine.py`（モデル読み込み・推論パラメータ）
      - `scripts/rt_stream.py`（ストリーミング入出力、VAD、KWS）

    設定の考え方:
    - FAST は“即時性優先”の軽量設定、FINAL は“精度優先”の重量設定にします。
    - CPU 前提では `compute_type=int8` が高速・省メモリ。GPU(CUDA)なら `float16` を推奨。
    - 本番環境で変更したいのは主にモデル名・ビーム幅・デバイス種別です。
    """

    # --- FAST stage（低遅延プレビュー） ---
    # 使用モデル名（faster-whisper のモデル識別子）
    FAST_MODEL = "small"
    # 推論の計算精度（CPU: int8/int8_float16、GPU: float16 など）
    FAST_COMPUTE = "int8"
    # ビームサーチ幅（小さいほど速いが、誤りやすくなる）
    FAST_BEAM = 2

    # --- FINAL stage（高精度確定） ---
    # 使用モデル名（高精度モデルを推奨）。Raspberry Pi 等の省メモリ環境では base/ small を推奨。
    FINAL_MODEL = "base"
    # 計算精度（GPU があるなら float16 を検討）
    FINAL_COMPUTE = "int8"
    # ビームサーチ幅（大きいほど精度は上がるが遅くなる）
    # Piでは負荷を抑えるため 3 程度から調整
    FINAL_BEAM = 3

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
    BLOCK_MS = 30
    # WebRTC VAD の攻撃性（0〜3：大きいほど“非音声”に厳しい）
    VAD_AGGRESSIVENESS = 2
    # 発話検出時に前後へ付与するパディング（ミリ秒）
    PAD_PREV_MS = 200
    PAD_POST_MS = 300

    # --- FINAL 実行制御 ---
    # FINAL を並列実行するワーカ数（スレッドプールの最大数）
    # Piではピークメモリを抑えるため 1 を推奨
    FINAL_MAX_WORKERS = 1
    # True にすると KWS ヒット時のみ FINAL を走らせる（遅延/負荷削減）。
    # FINALモデルの常時実行がメモリ圧迫・強制終了を招く環境向けの安全策。
    FINAL_ON_HIT_ONLY = True

    # --- KWS（キーワード検出） ---
    # かな正規化後の rapidfuzz.partial_ratio のしきい値（0〜100）
    KWS_FUZZY_THRESHOLD = 88

    # --- ASR 初期プロンプト（任意） ---
    # スタイル/固有名詞の事前ヒントなどを与えたい場合のテキストパス
    INITIAL_PROMPT_PATH = None
