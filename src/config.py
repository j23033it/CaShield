# src/config.py

# Audio settings
SAMPLE_RATE = 16000  # Whisperの要件に合わせて16kHzに設定
CHUNK_SIZE = 1024
CHANNELS = 1
FORMAT = "int16"  # pyaudio.paInt16 に対応するNumpyのデータ型

# Transcription settings
WHISPER_MODEL = "tiny"  # "tiny", "base", "small", "medium", "large" から選択
RECORD_SECONDS = 5  # 5秒ごとに文字起こしを実行
ENERGY_THRESHOLD = 300  # 音声と判断するエネルギーしきい値

# Action settings
ALERT_SOUND_PATH = "assets/alert.wav"  # 警告音ファイルのパス
LOG_FILE_PATH = "logs/harassment_log.txt"
KEYWORDS_FILE_PATH = "configurations/keywords.txt"

# Status messages
STATUS_LISTENING = "準備完了。音声を待っています..."
STATUS_RECORDING = "音声を検知。録音中..."
STATUS_TRANSCRIBING = "文字起こし中..."
STATUS_ACTION = "キーワードを検知！"
STATUS_ERROR = "エラーが発生しました。"
