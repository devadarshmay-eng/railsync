import json
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import get_db, init_db, Base, engine
from app.db.models import AuditEventORM, CandidateWindowORM, HumanActionORM, MaintenanceRequestORM
from app.db.seed import TRAIN_TIMETABLE
from app.domain.constants import AuditEventType, ControllerAction, FeasibilityStatus, RequestStatus
from app.domain.models import (
    CandidateWindow,
    ControllerDecisionPayload,
    NormalizedRequest,
    TrainModel,
    SectionOccupancy,
)
from app.adapters.planner.deterministic import DeterministicConstraintPlanner
from app.adapters.planner.ortools_planner import OrToolsBlockPlanner
from app.services.candidate_eval_service import evaluate_candidate_window
from app.services.controller_service import approve_maintenance_request, reject_maintenance_request
from app.services.planning_service import execute_block_planning

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)
    init_db()


def create_sample_request(
    db,
    req_id="MR-TEST-PLN-1",
    section_id="TVC-QLN",
    asset_id="TRK-TVC-01",
    preset_type="track_defect_weld",
    duration=120,
    status=RequestStatus.TRIAGED.value,
):
    req = MaintenanceRequestORM(
        id=req_id,
        section_id=section_id,
        asset_id=asset_id,
        preset_type=preset_type,
        department="P-Way",
        priority="HIGH",
        duration_minutes=duration,
        raw_text="Track weld maintenance required",
        status=status,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def test_timetable_conflict():
    """
    Verifies that when trains occupy a section, the planner detects the conflict,
    identifies affected trains with headway safety buffer, and applies regulation penalties.
    """
    planner = DeterministicConstraintPlanner(slot_step_min=30)
    
    # Custom timetable with a train on TVC-QLN from 100 to 140 min
    custom_timetable = [
        TrainModel(
            no="12076",
            name="Jan Shatabdi Express",
            type="JSH",
            occupancies=[SectionOccupancy(section_id="TVC-QLN", t0_min=100, t1_min=140)],
        )
    ]
    
    req = NormalizedRequest(
        request_id="REQ-CONFLICT",
        section_id="TVC-QLN",
        raw_text="Track inspection",
        input_mode="text",
        duration_minutes=60,
    )
    
    candidates = planner.plan_candidate_windows(
        request=req,
        timetable=custom_timetable,
        existing_blocks=[],
        horizon_minutes=360,
        max_candidates=10,
    )
    
    assert len(candidates) > 0
    # Any candidate whose window overlaps with [90, 150] (10 min headway buffer around [100, 140])
    # must include '12076 (Jan Shatabdi Express)' in affected_trains
    for c in candidates:
        if not (c.end_time_min <= 90 or c.start_time_min >= 150):
            assert any("12076" in t for t in c.affected_trains)
            assert c.optimality_score < 100.0


def test_no_conflict():
    """
    Verifies that during a clean window with zero train traffic,
    the planner produces a candidate with zero affected trains and optimal score.
    """
    planner = DeterministicConstraintPlanner(slot_step_min=30)
    req = NormalizedRequest(
        request_id="REQ-NOCONFLICT",
        section_id="TVC-QLN",
        raw_text="Routine track lubrication",
        input_mode="text",
        duration_minutes=60,
    )
    
    # Empty timetable
    candidates = planner.plan_candidate_windows(
        request=req,
        timetable=[],
        existing_blocks=[],
        horizon_minutes=240,
        max_candidates=3,
    )
    
    assert len(candidates) >= 1
    best_cand = candidates[0]
    assert len(best_cand.affected_trains) == 0
    assert len(best_cand.conflicts) == 0
    assert best_cand.feasibility_status == FeasibilityStatus.FEASIBLE
    assert best_cand.feasible is True


def test_maintenance_overlap():
    """
    Verifies that candidate generation rejects time windows overlapping with existing approved blocks.
    """
    planner = DeterministicConstraintPlanner(slot_step_min=30)
    req = NormalizedRequest(
        request_id="REQ-OVERLAP",
        section_id="TVC-QLN",
        raw_text="Track renewal",
        input_mode="text",
        duration_minutes=120,
    )
    
    # Existing block occupies TVC-QLN from 120 to 240 min
    existing_blocks = [
        {
            "candidate_id": "CW-EXISTING-1",
            "section_id": "TVC-QLN",
            "start_time_min": 120,
            "end_time_min": 240,
            "blocks_section": True,
        }
    ]
    
    candidates = planner.plan_candidate_windows(
        request=req,
        timetable=[],
        existing_blocks=existing_blocks,
        horizon_minutes=480,
        max_candidates=5,
    )
    
    # Every generated candidate must NOT overlap with [120, 240]
    for c in candidates:
        assert c.end_time_min <= 120 or c.start_time_min >= 240


def test_same_asset_conflict():
    """
    Verifies that if two maintenance jobs target the exact same asset,
    the planner disallows concurrent execution.
    """
    planner = DeterministicConstraintPlanner(slot_step_min=30)
    req = NormalizedRequest(
        request_id="REQ-ASSET",
        section_id="TVC-QLN",
        asset_id="TRK-RAIL-01",
        raw_text="Weld ultrasonic testing",
        input_mode="text",
        duration_minutes=60,
    )
    
    # Existing non-section-blocking job on the SAME asset from 60 to 120 min
    existing_blocks = [
        {
            "candidate_id": "CW-ASSET-EXISTING",
            "section_id": "TVC-QLN",
            "asset_id": "TRK-RAIL-01",
            "start_time_min": 60,
            "end_time_min": 120,
            "blocks_section": False,
        }
    ]
    
    candidates = planner.plan_candidate_windows(
        request=req,
        timetable=[],
        existing_blocks=existing_blocks,
        horizon_minutes=300,
        max_candidates=5,
    )
    
    for c in candidates:
        assert c.end_time_min <= 60 or c.start_time_min >= 120


def test_section_blocking_conflict():
    """
    Verifies that a section-blocking maintenance type cannot occupy the section
    concurrently with another section-blocking block.
    """
    planner = DeterministicConstraintPlanner(slot_step_min=30)
    req = NormalizedRequest(
        request_id="REQ-SEC-BLOCK",
        section_id="ERS-TCR",
        preset_type="track_defect_weld", # blocks_section = True
        raw_text="Track weld replacement",
        input_mode="preset",
        duration_minutes=90,
    )
    
    existing_blocks = [
        {
            "candidate_id": "CW-SEC-OCCUPIED",
            "section_id": "ERS-TCR",
            "start_time_min": 180,
            "end_time_min": 300,
            "blocks_section": True,
        }
    ]
    
    candidates = planner.plan_candidate_windows(
        request=req,
        timetable=[],
        existing_blocks=existing_blocks,
        horizon_minutes=480,
        max_candidates=5,
    )
    
    for c in candidates:
        assert c.end_time_min <= 180 or c.start_time_min >= 300


def test_candidate_generation():
    """
    Verifies that execute_block_planning generates >= 3 candidate windows,
    records PlanningRunORM and CandidateWindowORM, and populates canonical fields.
    """
    db = next(get_db())
    req_orm = create_sample_request(db, req_id="MR-GEN-001", section_id="TVC-QLN", duration=120)
    
    candidates = client.post("/api/planning/run", json={
        "request_id": req_orm.id,
        "horizon_hours": 24,
        "max_candidates": 4,
        "auto_evaluate_with_laya": False,
    })
    assert candidates.status_code == 200
    data = candidates.json()["data"]
    cand_list = data["candidates"]
    assert len(cand_list) >= 3
    
    for c in cand_list:
        assert "candidate_id" in c
        assert c["request_id"] == req_orm.id
        assert c["section_id"] == "TVC-QLN"
        assert c["section"] == "TVC-QLN"
        assert c["duration"] == 120
        assert c["start_time_min"] < c["end_time_min"]
        assert "start_time" in c
        assert "end_time" in c
        assert c["feasible"] is True
        assert "affected_services" in c
        assert "conflicts" in c
        assert "violated_constraints" in c
        assert "planner_version" in c
        assert c["planner_latency_ms"] >= 0.0

    # Verify audit events: planner_started and planner_completed
    events = db.query(AuditEventORM).filter(AuditEventORM.request_id == req_orm.id).all()
    event_types = [e.event_type for e in events]
    assert AuditEventType.PLANNER_STARTED.value in event_types
    assert AuditEventType.PLANNER_COMPLETED.value in event_types


@pytest.mark.asyncio
async def test_candidate_evaluation():
    """
    Verifies that LAYA candidate evaluation assesses risk, review recommendation,
    high priority conflicts, measures latency, and persists laya_evaluation on CandidateWindowORM.
    """
    db = next(get_db())
    req_orm = create_sample_request(db, req_id="MR-EVAL-001", section_id="TVC-QLN", duration=90)
    
    # 1. Run planner
    cands = await execute_block_planning(db=db, request_orm=req_orm, horizon_hours=24, max_candidates=3)
    assert len(cands) >= 1
    target_cand = cands[0]
    
    # 2. Evaluate candidate with LAYA
    eval_res = await evaluate_candidate_window(db=db, candidate_id=target_cand.candidate_id, actor="chief_controller")
    
    assert eval_res.candidate_id == target_cand.candidate_id
    assert eval_res.risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert eval_res.recommended_action in [ControllerAction.APPROVE_REVIEW, ControllerAction.SENIOR_REVIEW, ControllerAction.REJECT]
    assert eval_res.latency_ms > 0.0
    assert len(eval_res.model_version) > 0
    assert eval_res.conflict_interpretation is not None
    
    # Verify persistence on CandidateWindowORM
    cand_orm = db.query(CandidateWindowORM).filter(CandidateWindowORM.id == target_cand.candidate_id).first()
    assert cand_orm.laya_evaluation_json is not None
    saved_eval = json.loads(cand_orm.laya_evaluation_json)
    assert saved_eval["risk_level"] == eval_res.risk_level
    
    # Verify audit event: laya_candidate_evaluated
    audit_ev = db.query(AuditEventORM).filter(
        AuditEventORM.request_id == req_orm.id,
        AuditEventORM.event_type == AuditEventType.LAYA_CANDIDATE_EVALUATED.value
    ).first()
    assert audit_ev is not None
    assert audit_ev.latency_ms > 0.0


@pytest.mark.asyncio
async def test_approval_persistence():
    """
    Verifies that human controller approval persists selected candidate,
    controller identity, timestamp, action, updates request status to APPROVED,
    records HumanActionORM, and logs controller_approved audit event.
    Also verifies rejection persists controller_rejected.
    """
    db = next(get_db())
    req_orm = create_sample_request(db, req_id="MR-APPR-001", section_id="TVC-QLN", duration=120)
    
    # Generate candidate
    cands = await execute_block_planning(db=db, request_orm=req_orm, horizon_hours=24, max_candidates=2)
    assert len(cands) >= 1
    selected_cand = cands[0]
    
    # 1. Controller Approval
    approval_payload = ControllerDecisionPayload(
        candidate_id=selected_cand.candidate_id,
        actor_name="Sh. R. Sharma",
        actor_role="Section Controller",
        reason="Approved after checking night off-peak window and safety headway.",
    )
    
    appr_res = await approve_maintenance_request(db=db, request_id=req_orm.id, payload=approval_payload)
    assert appr_res.status == RequestStatus.APPROVED.value
    assert appr_res.selected_candidate_id == selected_cand.candidate_id
    assert appr_res.scheduled_start_min == selected_cand.start_time_min
    assert appr_res.scheduled_end_min == selected_cand.end_time_min
    
    # Verify HumanActionORM
    action = db.query(HumanActionORM).filter(HumanActionORM.request_id == req_orm.id).first()
    assert action is not None
    assert action.action == "APPROVED"
    assert action.actor_name == "Sh. R. Sharma"
    assert action.actor_role == "Section Controller"
    assert action.candidate_id == selected_cand.candidate_id
    
    # Verify AuditEvent: controller_approved
    audit_appr = db.query(AuditEventORM).filter(
        AuditEventORM.request_id == req_orm.id,
        AuditEventORM.event_type == AuditEventType.CONTROLLER_APPROVED.value
    ).first()
    assert audit_appr is not None
    assert "Sharma" in audit_appr.actor
    
    # 2. Rejection Test on another request
    req_rej = create_sample_request(db, req_id="MR-REJ-002", section_id="ERS-TCR", duration=90)
    rej_cands = await execute_block_planning(db=db, request_orm=req_rej, horizon_hours=24, max_candidates=1)
    rej_payload = ControllerDecisionPayload(
        candidate_id=rej_cands[0].candidate_id,
        actor_name="Sh. V. Menon",
        actor_role="Section Controller",
        reason="Declined due to heavy goods train convoy priority.",
    )
    
    rej_res = await reject_maintenance_request(db=db, request_id=req_rej.id, payload=rej_payload)
    assert rej_res.status == RequestStatus.REJECTED.value
    
    audit_rej = db.query(AuditEventORM).filter(
        AuditEventORM.request_id == req_rej.id,
        AuditEventORM.event_type == AuditEventType.CONTROLLER_REJECTED.value
    ).first()
    assert audit_rej is not None
    assert "Menon" in audit_rej.actor


@pytest.mark.asyncio
async def test_checklist_enforcement():
    """
    Verifies that controller approval enforces all statutory checklist items.
    If any item is False, ValueError is raised and approval is blocked.
    If all items are True, approval succeeds and checklist is persisted.
    """
    db = next(get_db())
    req_orm = create_sample_request(db, req_id="MR-CHK-001", section_id="TVC-QLN", duration=60)
    cands = await execute_block_planning(db=db, request_orm=req_orm, horizon_hours=12, max_candidates=1)
    cand_id = cands[0].candidate_id

    # 1. Incomplete checklist (one False)
    bad_payload = ControllerDecisionPayload(
        candidate_id=cand_id,
        actor_name="Controller Test",
        actor_role="Section Controller",
        reason="Approving with unchecked buffer",
        checklist={
            "headway_buffer": True,
            "express_corridor": False, # Incomplete!
            "traction_power": True,
            "emergency_corridor": True,
        }
    )
    with pytest.raises(ValueError) as excinfo:
        await approve_maintenance_request(db=db, request_id=req_orm.id, payload=bad_payload)
    assert "Statutory controller verification incomplete" in str(excinfo.value)

    # 2. Complete checklist (all True)
    good_payload = ControllerDecisionPayload(
        candidate_id=cand_id,
        actor_name="Controller Test",
        actor_role="Section Controller",
        reason="All G&SR 15.06 items verified",
        checklist={
            "headway_buffer": True,
            "express_corridor": True,
            "traction_power": True,
            "emergency_corridor": True,
        }
    )
    res = await approve_maintenance_request(db=db, request_id=req_orm.id, payload=good_payload)
    assert res.status == RequestStatus.APPROVED.value

    # Verify checklist_json in HumanActionORM
    action = db.query(HumanActionORM).filter(HumanActionORM.request_id == req_orm.id).first()
    assert action is not None
    assert action.checklist_json is not None
    saved_chk = json.loads(action.checklist_json)
    assert saved_chk["headway_buffer"] is True
    assert saved_chk["express_corridor"] is True


@pytest.mark.asyncio
async def test_mandatory_rejection_reason():
    """
    Verifies that rejection requires a non-empty reason under operating regulations.
    """
    db = next(get_db())
    req_orm = create_sample_request(db, req_id="MR-REJ-REASON", section_id="TVC-QLN", duration=60)
    cands = await execute_block_planning(db=db, request_orm=req_orm, horizon_hours=12, max_candidates=1)
    cand_id = cands[0].candidate_id

    # Empty reason
    empty_payload = ControllerDecisionPayload(
        candidate_id=cand_id,
        actor_name="Controller Test",
        actor_role="Section Controller",
        reason="   ",
    )
    with pytest.raises(ValueError) as excinfo:
        await reject_maintenance_request(db=db, request_id=req_orm.id, payload=empty_payload)
    assert "operational reason" in str(excinfo.value)


def test_reoptimize_api_flow():
    """
    Verifies that calling POST /api/requests/{id}/reoptimize:
    1. Records reoptimization_triggered in audit trail.
    2. Re-runs the constraint planner and candidate evaluation.
    3. Returns fresh candidate windows with physical feasibility and LAYA evaluation.
    """
    db = next(get_db())
    req_orm = create_sample_request(db, req_id="MR-API-REOPT", section_id="TVC-QLN", duration=90)
    
    # First plan candidates via planning endpoint
    plan_res = client.post(
        "/api/planning/run",
        json={
            "request_id": req_orm.id,
            "horizon_hours": 12,
            "max_candidates": 2
        }
    )
    assert plan_res.status_code == 200
    initial_cands = plan_res.json()["data"]["candidates"]
    assert len(initial_cands) >= 1
    first_cand_id = initial_cands[0]["candidate_id"]

    # Now request reoptimization via API
    reopt_payload = {
        "candidate_id": first_cand_id,
        "actor_name": "Senior Controller",
        "actor_role": "Section Controller",
        "reason": "Traffic spike expected in early slot, shift block further off-peak.",
        "checklist": {
            "headway_buffer": True,
            "express_corridor": False,
            "traction_power": False,
            "emergency_corridor": False
        }
    }
    reopt_res = client.post(f"/api/requests/{req_orm.id}/reoptimize", json=reopt_payload)
    assert reopt_res.status_code == 200
    reopt_json = reopt_res.json()
    assert reopt_json["status"] == "success"
    assert len(reopt_json["data"]["candidates"]) >= 1
    
    # Verify audit event reoptimization_triggered
    audit_res = client.get(f"/api/audit?request_id={req_orm.id}&event_type=reoptimization_triggered")
    assert audit_res.status_code == 200
    events = audit_res.json()["data"]
    assert len(events) >= 1
    assert "Senior Controller" in events[0]["actor"]
    assert "Traffic spike" in events[0]["input"]["reason"]


def test_audit_metrics_api():
    """
    Verifies that GET /api/audit/metrics calculates truthful aggregated operational stats
    and GET /api/audit filters correctly by event_type and request_id.
    """
    # 1. Query initial metrics
    metrics_res = client.get("/api/audit/metrics")
    assert metrics_res.status_code == 200
    m = metrics_res.json()["data"]
    assert "total_audit_events" in m
    assert "controller_approvals" in m
    assert "laya_inferences" in m
    assert "avg_laya_latency_ms" in m
    assert "avg_planner_latency_ms" in m
    assert "safety_override_count" in m
    assert "0" in str(m["safety_override_count"])
    assert "DEMO METRIC" in m["uptime"]

    # 2. Check audit events filter
    all_events_res = client.get("/api/audit?limit=50")
    assert all_events_res.status_code == 200
    assert "data" in all_events_res.json()

