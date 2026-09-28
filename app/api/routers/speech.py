from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session
from app.adapters.asr import get_asr_adapter
from app.core.audit import log_audit_event
from app.core.safety import get_safety_headers
from app.db.database import get_db
from app.domain.constants import AuditEventType
from app.domain.models import ASRResult

router = APIRouter(prefix="/api/speech", tags=["Speech-to-Text Pipeline"])


@router.post("/transcribe")
async def transcribe_audio_endpoint(
    response: Response,
    audio: UploadFile = File(...),
    language: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Transcribes an incoming audio chunk using the local ASR adapter (Whisper / Indic ASR).
    Measures genuine wall-clock latency, records immutable audit events, and purges
    raw audio from memory without permanent retention.
    """
    response.headers.update(get_safety_headers())
    asr_adapter = get_asr_adapter()

    content = await audio.read()
    if not content or len(content) < 32:
        raise HTTPException(status_code=400, detail="Empty or insufficient audio content provided.")

    # 1. Audit: voice_input_started
    await log_audit_event(
        db=db,
        event_type=AuditEventType.VOICE_INPUT_STARTED.value,
        actor="Operator Voice Input",
        input_payload={
            "audio_size_bytes": len(content),
            "filename": audio.filename or "recording.wav",
            "requested_language": language,
            "engine": asr_adapter.get_engine_name(),
        },
        metadata={"content_type": audio.content_type},
    )

    try:
        result: ASRResult = await asr_adapter.transcribe_audio_chunk(
            audio_bytes=content,
            sample_rate=16000,
            language=language,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ASR transcription failed: {str(e)}")

    # 2. Audit: transcription_completed
    await log_audit_event(
        db=db,
        event_type=AuditEventType.TRANSCRIPTION_COMPLETED.value,
        actor=asr_adapter.get_engine_name(),
        output_payload={
            "transcript": result.transcript,
            "detected_language": result.detected_language,
            "confidence": result.confidence,
            "audio_duration_ms": result.audio_duration_ms,
        },
        latency_ms=result.latency_ms,
        model_version=asr_adapter.get_engine_name(),
        decision="TRANSCRIPTION_SUCCESS",
    )

    return {
        "status": "success",
        "data": {
            "transcript": result.transcript,
            "detected_language": result.detected_language,
            "confidence": result.confidence,
            "latency_ms": result.latency_ms,
            "audio_duration_ms": result.audio_duration_ms,
            "asr_engine": asr_adapter.get_engine_name(),
        }
    }
