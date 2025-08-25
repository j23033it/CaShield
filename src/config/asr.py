class ASRConfig:
    """
    Code-based configuration for two-stage ASR (FAST/FINAL).

    Consolidates model, compute, beams, VAD, and other parameters here
    instead of .env. Import and use directly from code.
    """

    # --- FAST stage (low-latency) ---
    FAST_MODEL = "small"
    FAST_COMPUTE = "int8"
    FAST_BEAM = 2

    # --- FINAL stage (high-accuracy) ---
    FINAL_MODEL = "large-v3"
    FINAL_COMPUTE = "int8"
    FINAL_BEAM = 5

    # --- Common ASR params ---
    DEVICE = "cpu"
    LANGUAGE = "ja"
    TEMPERATURE = 0.0
    LOG_PROB_THRESHOLD = -0.8
    NO_SPEECH_THRESHOLD = 0.6
    VAD_FILTER = True  # Input is VAD-trimmed, keep configurable

    # --- Streaming / VAD frontend ---
    SAMPLE_RATE = 16000
    BLOCK_MS = 30
    VAD_AGGRESSIVENESS = 2
    PAD_PREV_MS = 200
    PAD_POST_MS = 300

    # --- FINAL stage execution control ---
    FINAL_MAX_WORKERS = 2
    # If True, run FINAL only when KWS hits. Default disabled.
    FINAL_ON_HIT_ONLY = False

    # --- KWS ---
    # rapidfuzz.fuzz.partial_ratio threshold on kana-normalized text
    KWS_FUZZY_THRESHOLD = 88

    # Optional: initial prompt for style or context priming
    INITIAL_PROMPT_PATH = None

