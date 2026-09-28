import io
import json
import wave
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import get_db, init_db, Base, engine
from app.db.models import AuditEventORM, MaintenanceRequestORM, LayaDecisionORM
from app.domain.constants import AuditEventType, RequestStatus
from app.domain.models import NormalizedRequest, RequestCreatePayload
from app.services.input_normalizer import normalize_request_input

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)
    init_db()


def make_synthetic_wav_bytes(duration_sec: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generates standard 16kHz mono PCM WAV bytes in-memory for testing."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        num_frames = int(sample_rate * duration_sec)
        w.writeframes(b"\x00\x00" * num_frames)
    return buf.getvalue()


def test_preset_input_normalization():
    """Validates structured preset input normalization."""
    payload = RequestCreatePayload(
        section="TVC-QLN",
        preset_type="track_defect_weld",
        department="P-Way",
        duration=120,
        priority="HIGH",
        input_mode="preset",
    )
    norm = normalize_request_input(payload)
    assert norm.input_mode == "preset"
    assert norm.section_id == "TVC-QLN"
    assert norm.department == "P-Way"
    assert norm.duration == 120
    assert norm.priority == "HIGH"
    assert "Preset: " in norm.raw_text


def test_free_text_input_normalization():
    """Validates free text input normalization."""
    payload = RequestCreatePayload(
        section="ERS-TCR",
        free_text="OHE catenary wire slack observed near km 68/4; urgent 90m block requested",
        department="TRD/OHE",
        duration=90,
        priority="CRITICAL",
        input_mode="text",
    )
    norm = normalize_request_input(payload)
    assert norm.input_mode == "text"
    assert norm.section_id == "ERS-TCR"
    assert norm.department == "TRD/OHE"
    assert norm.duration == 90
    assert norm.priority == "CRITICAL"
    assert "OHE catenary wire slack" in norm.raw_text


def test_voice_transcript_normalization():
    """Validates that voice transcripts produce the identical canonical NormalizedRequest schema."""
    payload = RequestCreatePayload(
        section="TVC-QLN",
        raw_text="Ultrasonic flaw detected on rail joint between TVC and QLN",
        language="en",
        input_mode="voice",
        department="P-Way",
        duration=120,
        priority="HIGH",
        metadata={
            "asr_engine": "OpenAI-Whisper@tiny",
            "asr_confidence": 0.94,
            "asr_latency_ms": 312.4,
        }
    )
    norm = normalize_request_input(payload)
    assert isinstance(norm, NormalizedRequest)
    assert norm.input_mode == "voice"
    assert norm.language == "en"
    assert norm.section_id == "TVC-QLN"
    assert norm.department == "P-Way"
    assert norm.duration == 120
    assert norm.metadata["asr_engine"] == "OpenAI-Whisper@tiny"
    assert norm.metadata["asr_confidence"] == 0.94


def test_section_inference_from_voice_transcript():
    """Validates smart extraction of railway section when spoken in raw transcript."""
    payload = RequestCreatePayload(
        raw_text="Emergency track caution between ERS and TCR due to heavy ballast wash-off",
        input_mode="voice",
        duration=180,
    )
    norm = normalize_request_input(payload)
    assert norm.section_id == "ERS-TCR"
    assert norm.duration == 180
    assert norm.input_mode == "voice"


def test_voice_transcribe_endpoint_valid_audio():
    """Tests POST /api/speech/transcribe with synthetic WAV bytes."""
    wav_bytes = make_synthetic_wav_bytes(duration_sec=1.0)
    
    response = client.post(
        "/api/speech/transcribe",
        files={"audio": ("test_recording.wav", wav_bytes, "audio/wav")},
        data={"language": "en"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "transcript" in data
    assert "detected_language" in data
    assert data["confidence"] > 0
    assert data["latency_ms"] > 0
    assert data["audio_duration_ms"] > 0
    assert "asr_engine" in data

    # Verify Audit Trail for voice input and transcription
    db = next(get_db())
    events = db.query(AuditEventORM).order_by(AuditEventORM.timestamp.asc()).all()
    event_types = [e.event_type for e in events]
    assert AuditEventType.VOICE_INPUT_STARTED.value in event_types
    assert AuditEventType.TRANSCRIPTION_COMPLETED.value in event_types


def test_voice_transcribe_empty_audio_rejection():
    """Tests rejection of empty audio content."""
    response = client.post(
        "/api/speech/transcribe",
        files={"audio": ("empty.wav", b"", "audio/wav")},
    )
    assert response.status_code == 400
    assert "Empty" in response.json()["detail"]


def test_voice_transcribe_corrupted_audio_rejection():
    """Tests rejection of corrupted, non-audio bytes."""
    corrupt_bytes = b"corrupted_invalid_non_audio_random_bytes_stream_12345678"
    response = client.post(
        "/api/speech/transcribe",
        files={"audio": ("corrupt.wav", corrupt_bytes, "audio/wav")},
    )
    assert response.status_code == 400
    assert "Invalid audio data" in response.json()["detail"]


def test_voice_request_full_lifecycle():
    """
    Validates complete canonical lifecycle for voice input:
    Microphone audio -> /api/speech/transcribe -> Transcript -> /api/requests -> LAYA Triage -> SQLite Persistence
    """
    wav_bytes = make_synthetic_wav_bytes(duration_sec=1.0)
    
    # 1. Transcribe audio chunk
    transcribe_res = client.post(
        "/api/speech/transcribe",
        files={"audio": ("field_recording.wav", wav_bytes, "audio/wav")},
        data={"language": "en"},
    )
    assert transcribe_res.status_code == 200
    trans_data = transcribe_res.json()["data"]

    # 2. Operator reviews transcript, edits, and submits request
    confirmed_transcript = "Track weld joint defect detected near TVC requiring immediate maintenance"
    req_payload = {
        "section": "TVC-QLN",
        "department": "P-Way",
        "priority": "HIGH",
        "duration": 120,
        "raw_text": confirmed_transcript,
        "input_mode": "voice",
        "language": trans_data["detected_language"],
        "metadata": {
            "asr_engine": trans_data["asr_engine"],
            "asr_confidence": trans_data["confidence"],
            "asr_latency_ms": trans_data["latency_ms"],
            "original_transcript": trans_data["transcript"],
        },
        "auto_triage": True,
    }

    create_res = client.post("/api/requests", json=req_payload)
    assert create_res.status_code in [200, 201]
    req_data = create_res.json()["data"]
    req_id = req_data["request_id"]
    assert req_data["status"] == "TRIAGED"
    assert req_data["input_mode"] == "voice"
    assert req_data["language"] == "en"

    # 3. Verify SQLite persistence of voice request and LAYA decision
    db = next(get_db())
    req_orm = db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.id == req_id).first()
    assert req_orm is not None
    assert req_orm.input_mode == "voice"
    assert req_orm.raw_text == confirmed_transcript
    assert req_orm.status == RequestStatus.TRIAGED.value

    dec_orm = db.query(LayaDecisionORM).filter(LayaDecisionORM.request_id == req_id).first()
    assert dec_orm is not None
    assert dec_orm.latency_ms > 0

    # 4. Verify immutable audit trail contains the full chronological chain
    events = db.query(AuditEventORM).filter(
        (AuditEventORM.request_id == req_id) | (AuditEventORM.event_type.in_([
            AuditEventType.VOICE_INPUT_STARTED.value,
            AuditEventType.TRANSCRIPTION_COMPLETED.value
        ]))
    ).order_by(AuditEventORM.timestamp.asc()).all()

    audit_types = [e.event_type for e in events]
    assert AuditEventType.VOICE_INPUT_STARTED.value in audit_types
    assert AuditEventType.TRANSCRIPTION_COMPLETED.value in audit_types
    assert AuditEventType.REQUEST_CREATED.value in audit_types
    assert AuditEventType.LAYA_TRIAGE_STARTED.value in audit_types
    assert AuditEventType.LAYA_TRIAGE_COMPLETED.value in audit_types
