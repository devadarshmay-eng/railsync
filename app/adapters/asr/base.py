from abc import ABC, abstractmethod
from typing import Optional
from app.domain.models import ASRResult


class SpeechToTextAdapter(ABC):
    """Abstract interface for speech-to-text engines with Indic language support."""

    @abstractmethod
    async def transcribe_audio_chunk(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        language: Optional[str] = None
    ) -> ASRResult:
        """Transcribe an audio chunk (16kHz mono) and return transcript with latency and confidence."""
        pass

    @abstractmethod
    def get_engine_name(self) -> str:
        """Returns name of the active ASR engine."""
        pass
