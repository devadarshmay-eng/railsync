import time
from typing import Optional
import httpx
from app.adapters.asr.base import SpeechToTextAdapter
from app.config import settings
from app.domain.models import ASRResult


class SarvamSpeechToTextAdapter(SpeechToTextAdapter):
    """Sarvam AI Indic STT API adapter supporting 10+ Indian languages with low latency."""

    def __init__(self, api_key: Optional[str] = None, endpoint: Optional[str] = None):
        self.api_key = api_key or settings.SARVAM_API_KEY
        self.endpoint = endpoint or settings.SARVAM_ENDPOINT

    def get_engine_name(self) -> str:
        return "Sarvam-AI-Indic-STT@v1"

    async def transcribe_audio_chunk(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        language: Optional[str] = None
    ) -> ASRResult:
        t0 = time.perf_counter()
        
        if not self.api_key:
            # Fallback if API key is not configured in local environment
            from app.adapters.asr.mock_adapter import MockSpeechToTextAdapter
            mock = MockSpeechToTextAdapter(engine_name="Sarvam-AI-Indic-Mock")
            res = await mock.transcribe_audio_chunk(audio_bytes, sample_rate, language)
            return res

        async with httpx.AsyncClient(timeout=10.0) as client:
            files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
            data = {"language_code": language or "hi-IN", "model": "saarika:v2"}
            headers = {"api-subscription-key": self.api_key}

            response = await client.post(self.endpoint, files=files, data=data, headers=headers)
            response.raise_for_status()
            res_data = response.json()

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return ASRResult(
            transcript=res_data.get("transcript", ""),
            detected_language=language or "indic",
            confidence=float(res_data.get("confidence", 0.95)),
            latency_ms=elapsed_ms,
            audio_duration_ms=round(len(audio_bytes) / 32.0, 1),
        )
