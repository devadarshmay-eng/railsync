from functools import lru_cache
from app.adapters.asr.base import SpeechToTextAdapter
from app.adapters.asr.mock_adapter import MockSpeechToTextAdapter
from app.adapters.asr.sarvam_adapter import SarvamSpeechToTextAdapter
from app.adapters.asr.whisper_adapter import WhisperSpeechToTextAdapter
from app.config import settings


@lru_cache(maxsize=1)
def get_asr_adapter() -> SpeechToTextAdapter:
    """Factory returning active ASR adapter."""
    engine = settings.ASR_ENGINE.lower()
    if engine == "whisper":
        return WhisperSpeechToTextAdapter(model_name=getattr(settings, "ASR_MODEL_NAME", "tiny"))
    elif engine == "sarvam":
        return SarvamSpeechToTextAdapter()
    return MockSpeechToTextAdapter()
