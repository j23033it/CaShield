# src/config (package)

# Audio settings
SAMPLE_RATE = 16000  # Whisperの要件に合わせて16kHzに設定
CHUNK_SIZE = 1024
CHANNELS = 1
FORMAT = "int16"  # pyaudio.paInt16 に対応するNumpyのデータ型

# Action settings
ALERT_SOUND_PATH = "assets/alert.wav"  # 警告音ファイルのパス
LOG_FILE_PATH = "logs/harassment_log.txt"
KEYWORDS_FILE_PATH = "config/keywords.txt" # main.pyのパスと合わせる

# Status messages
STATUS_LISTENING = "準備完了。音声を待っています..."
STATUS_RECORDING = "音声を検知。録音中..."
STATUS_TRANSCRIBING = "文字起こし中..."
STATUS_ACTION = "キーワードを検知！"
STATUS_ERROR = "エラーが発生しました。"

# Whisper settings
WHISPER_MODEL = "small" # "tiny", "base", "small", "medium", "large-v2", "large-v3"
DEVICE        = "cpu"      # GPU があれば "cuda"
COMPUTE_TYPE  = "int8"     # CPU: int8/int8_float16, GPU: float16
LANGUAGE      = "ja"
BEAM_SIZE     = 5
TEMPERATURE   = 0.0
VAD_FILTER    = True

