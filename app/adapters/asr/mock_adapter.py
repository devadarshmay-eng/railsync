import time
from typing import Optional
from app.adapters.asr.base import SpeechToTextAdapter
from app.domain.models import ASRResult


class MockSpeechToTextAdapter(SpeechToTextAdapter):
    """Deterministic, zero-dependency ASR adapter for testing and benchmarking."""

    def __init__(self, engine_name: str = "IndicASR-Mock@1.0"):
        self.engine_name = engine_name

    def get_engine_name(self) -> str:
        return self.engine_name

    async def transcribe_audio_chunk(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        language: Optional[str] = None
    ) -> ASRResult:
        if not audio_bytes or len(audio_bytes) < 32:
            raise ValueError("Empty or insufficient audio content provided.")
        if b"corrupt" in audio_bytes.lower() or audio_bytes == b"INVALID_AUDIO_BYTES":
            raise ValueError("Invalid audio data: unrecognized audio container or corrupted stream.")
        if audio_bytes == b"SIMULATE_ASR_FAILURE":
            raise RuntimeError("ASR transcription engine failure: simulated hardware error.")

        t0 = time.perf_counter()
        
        # Audio length approximation from raw bytes (16-bit PCM = 2 bytes per sample)
        duration_sec = len(audio_bytes) / (sample_rate * 2) if audio_bytes else 1.5
        duration_ms = round(duration_sec * 1000.0, 1)

        # Realistic railway maintenance transcription
        lang = language or "en"
        if lang == "ml": # Malayalam
            transcript = "എറണാകുളം തൃശൂർ സെക്ഷനിൽ ട്രാക്ക് വെൽഡ് തകരാർ ഉണ്ട് അടിയന്തര ബ്ലോക്ക് വേണം"
        elif lang == "hi": # Hindi
            transcript = "एर्नाकुलम त्रिशूर सेक्शन में रेल वेल्ड दरार है तुरंत ब्लॉक की आवश्यकता है"
        elif lang == "ta": # Tamil
            transcript = "கொல்லம் காயம்குளம் பிரிவில் தண்டவாள வெல்டிங் பழுது ஏற்பட்டுள்ளது உடனடியாக பிளாக் தேவை"
        else:
            transcript = "Rail weld defect detected between TVC and QLN requiring immediate 2-hour maintenance block"

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        if elapsed_ms == 0.0:
            elapsed_ms = 4.2

        return ASRResult(
            transcript=transcript,
            detected_language=lang,
            confidence=0.94,
            latency_ms=elapsed_ms,
            audio_duration_ms=duration_ms,
        )
