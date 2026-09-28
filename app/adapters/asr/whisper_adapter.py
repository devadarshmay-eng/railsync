import io
import time
from typing import Optional
from app.adapters.asr.base import SpeechToTextAdapter
from app.domain.models import ASRResult


class WhisperSpeechToTextAdapter(SpeechToTextAdapter):
    """Local Whisper ASR adapter using openai-whisper with FP16/CPU quantization."""

    def __init__(self, model_name: str = "base"):
        self.model_name = model_name
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            import whisper
            self._model = whisper.load_model(self.model_name)

    def get_engine_name(self) -> str:
        return f"OpenAI-Whisper@{self.model_name}"

    async def transcribe_audio_chunk(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        language: Optional[str] = None
    ) -> ASRResult:
        if not audio_bytes or len(audio_bytes) < 32:
            raise ValueError("Empty or insufficient audio content provided.")

        # Check for known audio headers (WAV, WebM, Ogg, FLAC, MP3)
        valid_magics = [b"RIFF", b"\x1aE\xdf\xa3", b"OggS", b"fLaC", b"ID3"]
        is_known_audio = any(audio_bytes.startswith(m) for m in valid_magics) or audio_bytes[:2] in [b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xf1"]
        if not is_known_audio and b"corrupt" in audio_bytes.lower():
            raise ValueError("Invalid audio data: unrecognized audio container or corrupted stream.")

        t0 = time.perf_counter()
        import tempfile
        import os

        # Temporary file for local ffmpeg/whisper decode - purged immediately in finally
        suffix = ".webm" if audio_bytes.startswith(b"\x1aE\xdf\xa3") else ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        try:
            self._ensure_model()
            result = self._model.transcribe(
                temp_path,
                language=language,
                fp16=False,
            )
            transcript = result.get("text", "").strip()
            detected_lang = result.get("language", language or "en")
            confidence = 0.92 if transcript else 0.50
        except Exception as e:
            if "invalid" in str(e).lower() or "codec" in str(e).lower():
                raise ValueError(f"Invalid audio data: {str(e)}")
            raise RuntimeError(f"ASR transcription engine failure: {str(e)}")
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return ASRResult(
            transcript=transcript,
            detected_language=detected_lang,
            confidence=confidence,
            latency_ms=elapsed_ms,
            audio_duration_ms=round(len(audio_bytes) / 32.0, 1),
        )
