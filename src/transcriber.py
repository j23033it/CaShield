# src/transcriber.py
from faster_whisper import WhisperModel
import src.config as cfg

# モデルは一度だけロード
_model = WhisperModel(
    cfg.WHISPER_MODEL,
    device       = cfg.DEVICE,
    compute_type = cfg.COMPUTE_TYPE
)

def transcribe(audio_path: str) -> str:
    segments, _ = _model.transcribe(
    audio_path,
    language    = cfg.LANGUAGE,
    beam_size   = cfg.BEAM_SIZE,
    temperature = cfg.TEMPERATURE,
    vad_filter  = True
    )
    text = "".join(seg.text for seg in segments)
