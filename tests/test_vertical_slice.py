import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import Base, engine, init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)
    init_db()


def test_complete_vertical_slice():
    # 1. Health check & Safety header verification
    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    assert res_health.headers.get("x-railsync-advisory") is not None
    assert "ADVISORY ONLY" in res_health.headers["x-railsync-advisory"]

    # 2. Submit maintenance request via Preset
    req_payload = {
        "section_id": "TVC-QLN",
        "preset_type": "track_defect_weld",
        "input_mode": "preset",
        "duration_minutes": 90,
    }
    res_req = client.post("/api/requests", json=req_payload)
    assert res_req.status_code == 201
    req_data = res_req.json()["data"]
    request_id = req_data["request_id"]
    assert request_id.startswith("MR-")
    assert req_data["status"] == "RECEIVED"

    # 3. LAYA Decision Engine (Point 1: Triage)
    res_triage = client.post(f"/api/requests/{request_id}/triage")
    assert res_triage.status_code == 200
    triage_data = res_triage.json()["data"]
    assert triage_data["department"]["label"] in ["P-Way", "S&T", "TRD", "Mechanical", "Operating"]
    assert triage_data["priority"]["label"] in ["HIGH", "CRITICAL", "NORMAL", "LOW"]
    assert triage_data["latency_ms"] > 0.0

    # Verify status transitioned to TRIAGED
    res_get = client.get(f"/api/requests/{request_id}")
    assert res_get.status_code == 200
    assert res_get.json()["data"]["status"] == "TRIAGED"

    # 4. Deterministic / OR-Tools Block Planning Engine
    res_plan = client.post("/api/planning/run", json={"request_id": request_id, "horizon_hours": 24, "max_candidates": 3})
    assert res_plan.status_code == 200
    plan_data = res_plan.json()["data"]
    assert plan_data["candidate_count"] > 0
    candidates = plan_data["candidates"]
    assert len(candidates) > 0
    first_candidate = candidates[0]
    candidate_id = first_candidate["candidate_id"]

    # 5. Second LAYA Decision Point: Candidate Window Evaluation
    res_eval = client.post(f"/api/candidates/{candidate_id}/evaluate")
    assert res_eval.status_code == 200
    eval_data = res_eval.json()["data"]
    assert eval_data["risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert eval_data["recommended_action"] in ["APPROVE_REVIEW", "SENIOR_REVIEW", "REJECT"]
    assert eval_data["latency_ms"] > 0.0

    # 6. Human Section Controller Approval
    approval_payload = {
        "candidate_id": candidate_id,
        "actor_name": "Sh. R. Sharma",
        "actor_role": "Section Controller",
        "reason": "Approved for execution in shadow night block window.",
    }
    res_appr = client.post(f"/api/requests/{request_id}/approve", json=approval_payload)
    assert res_appr.status_code == 200
    assert res_appr.json()["data"]["status"] == "APPROVED"

    # Verify metrics reflects approved request
    res_metrics_appr = client.get("/api/metrics")
    assert res_metrics_appr.status_code == 200
    assert res_metrics_appr.json()["metrics"]["approved"] >= 1

    # 7. Audit Trail Verification
    res_audit = client.get(f"/api/audit?request_id={request_id}")
    assert res_audit.status_code == 200
    events = res_audit.json()["data"]
    event_types = [e["event_type"] for e in events]
    assert "request_created" in event_types
    assert "laya_triage_completed" in event_types
    assert "planner_completed" in event_types
    assert "controller_approved" in event_types

    # 8. What-If Incident Engine Simulation
    incident_payload = {
        "incident_type": "SIGNAL_MALFUNCTION",
        "section_id": "TVC-QLN",
        "description": "Down home signal S-14 blanking due to cable damage",
        "expected_delay_min": 35
    }
    res_inc = client.post("/api/incidents/simulate", json=incident_payload)
    assert res_inc.status_code == 200
    inc_data = res_inc.json()["data"]
    assert inc_data["triggers_reoptimization"] is True

    # 9. Verify request automatically transitioned to REOPTIMIZATION_REQUIRED after incident
    res_get_reopt = client.get(f"/api/requests/{request_id}")
    assert res_get_reopt.status_code == 200
    assert res_get_reopt.json()["data"]["status"] == "REOPTIMIZATION_REQUIRED"

    # 10. Verify Telemetry reflects measured latencies
    res_metrics = client.get("/api/metrics")
    assert res_metrics.status_code == 200
    metrics = res_metrics.json()["metrics"]
    assert metrics["total_requests"] >= 1
    assert metrics["measured_laya_avg_latency_ms"] > 0.0
    assert metrics["measured_planner_avg_latency_ms"] > 0.0
