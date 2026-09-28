import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import get_db, init_db, Base, engine
from app.db.models import AuditEventORM, MaintenanceRequestORM, IncidentORM
from app.domain.constants import AuditEventType, IncidentType, RequestStatus
from app.domain.models import IncidentSimulationPayload
from app.services.incident_service import simulate_and_evaluate_incident

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)
    init_db()


def create_approved_block(
    db,
    req_id="MR-APPROVED-01",
    section_id="TVC-QLN",
    start_min=450,
    end_min=570,
    duration=120,
):
    """Creates a sample approved maintenance block in SQLite."""
    req = MaintenanceRequestORM(
        id=req_id,
        section_id=section_id,
        asset_id="TRK-TVC-01",
        preset_type="track_defect_weld",
        department="P-Way",
        priority="HIGH",
        duration_minutes=duration,
        scheduled_start_min=start_min,
        scheduled_end_min=end_min,
        selected_candidate_id="CW-INIT-01",
        raw_text="Track weld maintenance possession",
        status=RequestStatus.APPROVED.value,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@pytest.mark.asyncio
async def test_train_delay_collision_detection():
    """
    Deterministic Collision Scenario:
    Train 12076 occupies TVC-QLN from 360 to 420 min.
    Approved block on TVC-QLN is scheduled from 450 to 570 min (safety buffer: 440 to 580 min).
    Inject 60 min delay -> train delayed occupancy is 420 to 480 min.
    480 > 440 -> Overlap of 40 minutes -> Timetable possession collision detected!
    """
    db = next(get_db())
    req = create_approved_block(db, req_id="MR-COLLIDE-01", section_id="TVC-QLN", start_min=450, end_min=570)

    payload = IncidentSimulationPayload(
        incident_type=IncidentType.TRAIN_DELAY,
        train_no="12076",
        expected_delay_min=60,
        description="60 min delay on Jan Shatabdi Express due to signaling snag",
    )

    result = await simulate_and_evaluate_incident(db=db, payload=payload, actor="Test Simulator")

    # 1. Authoritative Physical Collision
    assert result.physical_collision_detected is True
    assert result.affects_active_block is True
    assert result.triggers_reoptimization is True
    assert len(result.collision_details) > 0
    assert result.collision_details[0]["train_no"] == "12076"
    assert result.collision_details[0]["request_id"] == "MR-COLLIDE-01"

    # 2. Block status transition to REOPTIMIZATION_REQUIRED (not silently replaced!)
    db.refresh(req)
    assert req.status == RequestStatus.REOPTIMIZATION_REQUIRED.value

    # 3. Constraint Planner generated fresh candidates
    assert result.reoptimization_status == "COMPLETED"
    assert len(result.new_candidates) > 0

    # 4. Candidates evaluated by LAYA
    for cand in result.new_candidates:
        assert cand.laya_evaluation is not None
        assert cand.laya_evaluation.risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

    # 5. Immutable Audit Trail verification
    events = db.query(AuditEventORM).order_by(AuditEventORM.timestamp.asc()).all()
    event_types = [e.event_type for e in events]

    assert AuditEventType.INCIDENT_CREATED.value in event_types
    assert AuditEventType.INCIDENT_EVALUATED.value in event_types
    assert AuditEventType.ACTIVE_BLOCK_AFFECTED.value in event_types
    assert AuditEventType.REOPTIMIZATION_TRIGGERED.value in event_types
    assert AuditEventType.REOPTIMIZATION_COMPLETED.value in event_types


@pytest.mark.asyncio
async def test_train_delay_non_collision_detection():
    """
    Deterministic Non-Collision Scenario:
    Train 12076 occupies TVC-QLN from 360 to 420 min.
    Approved block on TVC-QLN is scheduled from 450 to 570 min (safety buffer: 440 to 580 min).
    Inject 10 min delay -> train delayed occupancy is 370 to 430 min.
    430 < 440 -> Train clears section 10 min before the maintenance buffer begins!
    No collision -> schedule remains valid!
    """
    db = next(get_db())
    req = create_approved_block(db, req_id="MR-NO-COLLIDE-01", section_id="TVC-QLN", start_min=450, end_min=570)

    payload = IncidentSimulationPayload(
        incident_type=IncidentType.TRAIN_DELAY,
        train_no="12076",
        expected_delay_min=10,
        description="10 min minor delay on Jan Shatabdi Express",
    )

    result = await simulate_and_evaluate_incident(db=db, payload=payload, actor="Test Simulator")

    # 1. Authoritative Physical Collision is False
    assert result.physical_collision_detected is False
    assert result.affects_active_block is False
    assert result.triggers_reoptimization is False
    assert result.reoptimization_status == "NOT_REQUIRED"
    assert len(result.new_candidates) == 0

    # 2. Approved block status remains APPROVED
    db.refresh(req)
    assert req.status == RequestStatus.APPROVED.value

    # 3. Audit trail records reoptimization_not_required
    events = db.query(AuditEventORM).order_by(AuditEventORM.timestamp.asc()).all()
    event_types = [e.event_type for e in events]

    assert AuditEventType.INCIDENT_CREATED.value in event_types
    assert AuditEventType.INCIDENT_EVALUATED.value in event_types
    assert AuditEventType.REOPTIMIZATION_NOT_REQUIRED.value in event_types
    assert AuditEventType.REOPTIMIZATION_TRIGGERED.value not in event_types


def test_whatif_api_simulate_collision_flow():
    """Validates the HTTP REST endpoint POST /api/incidents/simulate for collision case."""
    db = next(get_db())
    create_approved_block(db, req_id="MR-API-01", section_id="TVC-QLN", start_min=450, end_min=570)

    response = client.post(
        "/api/incidents/simulate",
        json={
            "incident_type": "Loco Failure",
            "train_no": "12076",
            "delay_min": 75,
            "description": "Locomotive power loss causing 75 min detention",
        }
    )

    assert response.status_code == 200
    assert response.headers.get("x-railsync-advisory") is not None

    data = response.json()["data"]
    assert data["physical_collision_detected"] is True
    assert data["affects_active_block"] is True
    assert data["triggers_reoptimization"] is True
    assert data["reoptimization_status"] == "COMPLETED"
    assert len(data["new_candidates"]) > 0
    assert len(data["mitigation_strategies"]) == 3


def test_whatif_api_simulate_no_collision_flow():
    """Validates the HTTP REST endpoint POST /api/incidents/simulate for clear window case."""
    db = next(get_db())
    create_approved_block(db, req_id="MR-API-02", section_id="TVC-QLN", start_min=450, end_min=570)

    response = client.post(
        "/api/incidents/simulate",
        json={
            "incident_type": "Signal Malfunction",
            "train_no": "12076",
            "delay_min": 5,
            "description": "Minor signal aspect flicker; 5 min delay",
        }
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["physical_collision_detected"] is False
    assert data["affects_active_block"] is False
    assert data["triggers_reoptimization"] is False
    assert data["reoptimization_status"] == "NOT_REQUIRED"
    assert len(data["new_candidates"]) == 0


@pytest.mark.asyncio
async def test_corridor_track_defect_incident():
    """Validates corridor section incident (Track Defect) directly colliding with active block."""
    db = next(get_db())
    req = create_approved_block(db, req_id="MR-DEFECT-01", section_id="TVC-QLN", start_min=450, end_min=570)

    payload = IncidentSimulationPayload(
        incident_type=IncidentType.TRACK_DEFECT,
        section_id="TVC-QLN",
        expected_delay_min=90,
        description="Weld fracture detected on TVC-QLN Up Line",
    )

    result = await simulate_and_evaluate_incident(db=db, payload=payload, actor="Track Supervisor")

    assert result.physical_collision_detected is True
    assert result.affects_active_block is True
    assert result.triggers_reoptimization is True

    db.refresh(req)
    assert req.status == RequestStatus.REOPTIMIZATION_REQUIRED.value
