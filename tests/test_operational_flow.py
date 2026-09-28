import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import Base, engine, init_db, get_db
from app.db.models import AuditEventORM, LayaDecisionORM, MaintenanceRequestORM
from app.domain.constants import AuditEventType, RequestStatus

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)
    init_db()


def test_create_request_via_preset():
    """Validates structured preset submission, normalization, and RECEIVED status."""
    payload = {
        "section": "TVC-QLN",
        "preset_type": "track_defect_weld",
        "input_mode": "preset",
        "duration": 120,
        "priority": "HIGH",
    }
    res = client.post("/api/requests", json=payload)
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["request_id"].startswith("MR-")
    assert data["section_id"] == "TVC-QLN"
    assert data["status"] == RequestStatus.RECEIVED.value
    assert data["duration_minutes"] == 120
    assert "Track Rail Weld Defect" in data["raw_text"]


def test_create_request_via_free_text():
    """Validates free-text submission with custom operator notes."""
    payload = {
        "section": "ERS-TCR",
        "free_text": "OHE contact wire hanging loose near Chalakudi station mast 62/14",
        "department": "TRD/OHE",
        "priority": "CRITICAL",
        "duration": 90,
    }
    res = client.post("/api/requests", json=payload)
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["section_id"] == "ERS-TCR"
    assert data["department"] == "TRD/OHE"
    assert data["priority"] == "CRITICAL"
    assert "OHE contact wire" in data["raw_text"]


def test_invalid_request_handling_400():
    """Verifies that requests with missing sections or negative durations return HTTP 400."""
    # 1. Missing section
    res1 = client.post("/api/requests", json={"free_text": "Broken rail", "duration": 60})
    assert res1.status_code == 400
    assert "Section is required" in res1.json()["detail"]

    # 2. Unknown railway section
    res2 = client.post("/api/requests", json={"section": "DEL-BOM", "free_text": "Track work"})
    assert res2.status_code == 400
    assert "Unknown railway section" in res2.json()["detail"]

    # 3. Negative duration
    res3 = client.post("/api/requests", json={"section": "TVC-QLN", "free_text": "Track work", "duration": -45})
    assert res3.status_code == 400
    assert "Duration must be a positive number" in res3.json()["detail"]


def test_laya_triage_flow_and_persistence():
    """
    Submits a maintenance request, executes LAYA System 1 triage,
    and validates persistence in SQLite and status transition to TRIAGED.
    """
    # 1. Create request
    payload = {
        "section": "TVC-QLN",
        "preset_type": "track_defect_weld",
        "free_text": "Rail weld crack detected during ultrasonic test",
    }
    res_create = client.post("/api/requests", json=payload)
    assert res_create.status_code == 201
    req_id = res_create.json()["data"]["request_id"]

    # 2. Trigger LAYA triage
    res_triage = client.post(f"/api/requests/{req_id}/triage")
    assert res_triage.status_code == 200
    triage_data = res_triage.json()["data"]

    # Verify decision structure and measured latency
    assert triage_data["department"]["label"] in ["P-Way", "S&T", "TRD", "Mechanical", "Operating"]
    assert triage_data["priority"]["label"] in ["HIGH", "CRITICAL", "NORMAL", "LOW"]
    assert triage_data["safety_critical"]["label"] in [True, False]
    assert triage_data["latency_ms"] > 0.0
    assert "laya" in triage_data["model_version"].lower()

    # 3. Verify SQLite persistence of MaintenanceRequestORM and LayaDecisionORM
    db = next(get_db())
    req_orm = db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.id == req_id).first()
    assert req_orm is not None
    assert req_orm.status == RequestStatus.TRIAGED.value
    assert req_orm.department == triage_data["department"]["label"]

    dec_orm = db.query(LayaDecisionORM).filter(LayaDecisionORM.request_id == req_id).first()
    assert dec_orm is not None
    assert dec_orm.decision_point == "TRIAGE"
    assert dec_orm.department == triage_data["department"]["label"]
    assert dec_orm.latency_ms > 0.0
    assert dec_orm.model_version == triage_data["model_version"]


def test_audit_event_generation():
    """
    Verifies that request_created, laya_triage_started, and laya_triage_completed
    are logged in the audit trail.
    """
    payload = {
        "section": "TCR-SRR",
        "free_text": "Signal aspect blanking on up line home signal",
        "auto_triage": True, # Test UI path where auto_triage=True
    }
    res = client.post("/api/requests", json=payload)
    assert res.status_code == 201
    req_id = res.json()["data"]["request_id"]

    # Inspect audit events in DB
    db = next(get_db())
    audit_events = db.query(AuditEventORM).filter(AuditEventORM.request_id == req_id).all()
    event_types = [e.event_type for e in audit_events]

    assert AuditEventType.REQUEST_CREATED.value in event_types
    assert AuditEventType.LAYA_TRIAGE_STARTED.value in event_types
    assert AuditEventType.LAYA_TRIAGE_COMPLETED.value in event_types


def test_laya_unavailable_error_handling():
    """
    Verifies that if the LAYA decision engine encounters an error,
    it returns HTTP 503 with informative diagnostics without crashing.
    """
    # 1. Create a request
    res = client.post("/api/requests", json={"section": "TVC-QLN", "free_text": "Ballast screening"})
    assert res.status_code == 201
    req_id = res.json()["data"]["request_id"]

    # 2. Simulate LAYA adapter raising an exception
    with patch("app.services.triage_service.get_laya_adapter") as mock_get_adapter:
        mock_adapter = MagicMock()
        mock_adapter.triage_request.side_effect = RuntimeError("GPU OutOfMemory: CUDA alloc failed")
        mock_get_adapter.return_value = mock_adapter

        res_err = client.post(f"/api/requests/{req_id}/triage")
        assert res_err.status_code == 503
        assert "LAYA Decision Engine unavailable" in res_err.json()["detail"]
        assert "GPU OutOfMemory" in res_err.json()["detail"]


def test_maintenance_queue_list_endpoint():
    """Verifies that GET /api/requests exposes triaged requests with real LAYA details."""
    # Create and triage a request
    client.post("/api/requests", json={
        "section": "TVC-QLN",
        "preset_type": "track_defect_weld",
        "auto_triage": True,
    })

    res_list = client.get("/api/requests")
    assert res_list.status_code == 200
    json_data = res_list.json()
    assert json_data["status"] == "success"
    assert json_data["count"] >= 1

    first_item = json_data["data"][0]
    assert first_item["status"] == "TRIAGED"
    assert first_item["triage"] is not None
    assert first_item["triage"]["department"]["label"] in ["P-Way", "S&T", "TRD", "Mechanical", "Operating"]
    assert first_item["triage"]["latency_ms"] > 0.0
