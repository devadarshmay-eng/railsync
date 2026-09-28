import pytest
from app.adapters.asr.mock_adapter import MockSpeechToTextAdapter


@pytest.mark.asyncio
async def test_asr_adapter_transcription():
    adapter = MockSpeechToTextAdapter()
    
    # Simulate 1 second of 16kHz mono audio (32,000 bytes)
    mock_audio = b"\x00" * 32000

    # 1. English
    res_en = await adapter.transcribe_audio_chunk(mock_audio, language="en")
    assert "weld" in res_en.transcript.lower() or "rail" in res_en.transcript.lower()
    assert res_en.detected_language == "en"
    assert res_en.confidence > 0.8
    assert res_en.latency_ms > 0.0

    # 2. Malayalam Indic
    res_ml = await adapter.transcribe_audio_chunk(mock_audio, language="ml")
    assert res_ml.detected_language == "ml"
    assert len(res_ml.transcript) > 0
    assert res_ml.latency_ms > 0.0

    # 3. Hindi Indic
    res_hi = await adapter.transcribe_audio_chunk(mock_audio, language="hi")
    assert res_hi.detected_language == "hi"
    assert len(res_hi.transcript) > 0
