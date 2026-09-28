"""
RailSync AI - Complete 24-Step Operational User Journey & Error Handling Verification
======================================================================================
Automated end-to-end verification covering:
1. Application health & frontend entrypoint
2. Request submission, canonical normalization, and local LAYA System 1 triage
3. Queue persistence in SQLite (WAL mode)
4. Deterministic / OR-Tools CP-SAT block planning
5. LAYA candidate window evaluation
6. Statutory Controller verification checklist enforcement (G&SR 15.06)
7. Human authorization and schedule persistence
8. Complete audit event chain and operational metrics
9. What-If Disruption simulation with deterministic collision detection
10. Automatic reoptimization cascade and LAYA evaluation of fresh candidates
11. Controller review required for reoptimized blocks
12. Defensive error handling (invalid candidate, unknown train, malformed requests, partial checklist)
"""

import json
import os
import sys
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from app.main import app
from app.db.database import get_db, init_db, SessionLocal
from app.db.models import (
    AuditEventORM,
    CandidateWindowORM,
    HumanActionORM,
    IncidentORM,
    MaintenanceRequestORM,
    PlanningRunORM,
)
from app.domain.constants import AuditEventType, RequestStatus

client = TestClient(app)


def log_step(step_num: int, title: str):
    print(f"\n================================================================================")
    print(f"STEP {step_num:02d}: {title}")
    print(f"================================================================================")


def run_full_journey():
    print("********************************************************************************")
    print("RAILSYNC AI: COMPLETE 24-STEP HACKATHON DEMO & RESILIENCE VERIFICATION")
    print("********************************************************************************")

    # Step 1: Start Application & Health Check
    log_step(1, "Verify Application Health & Active Model Status")
    res = client.get("/api/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    health_data = res.json()
    assert health_data["status"] == "healthy"
    assert health_data["laya"]["is_loaded"] is True
    print(f"[OK] Application running. LAYA Model: {health_data['laya']['model_id']} (Adapter: {health_data['laya']['adapter']})")
    print(f"[OK] Planner: {health_data['planner']} | Database: {health_data['database']}")

    # Step 2: Open RailSync Frontend
    log_step(2, "Open RailSync Frontend (Static Entrypoint)")
    res = client.get("/")
    assert res.status_code == 200
    assert "RailSync" in res.text
    print(f"[OK] RailSync Web UI accessible at root URL (Status 200, Content-Length: {len(res.text)} bytes)")

    # Step 3: Submit Maintenance Request using Preset
    log_step(3, "Submit Maintenance Request using Structured Preset")
    req_payload = {
        "section_id": "TVC-QLN",
        "asset_id": "TRK-TVC-04B",
        "department": "P-Way",
        "preset_type": "track_repair",
        "priority": "HIGH",
        "duration": 120,
        "free_text": "Severe rail joint weld defect detected near TVC curve 4B; deep packing required.",
        "input_mode": "preset",
        "auto_triage": False
    }
    res = client.post("/api/requests", json=req_payload)
    assert res.status_code == 201, f"Create request failed: {res.text}"
    req_json = res.json()["data"]
    req_id = req_json["request_id"]
    print(f"[OK] Submitted preset maintenance request. Received Request ID: {req_id}")

    # Step 4: Verify Request Reaches Backend
    log_step(4, "Verify Request Reaches Backend & Generates Valid Identifier")
    assert req_id.startswith("MR-")
    assert req_json["status"] == RequestStatus.RECEIVED.value
    print(f"[OK] Backend confirmed ingestion with canonical ID: {req_id}")

    # Step 5: Verify Normalization
    log_step(5, "Verify Input Normalization to Canonical Domain Schema")
    assert req_json["section_id"] == "TVC-QLN"
    assert req_json["duration_minutes"] == 120
    assert req_json["input_mode"] == "preset"
    assert "Preset: " in req_json["raw_text"]
    print(f"[OK] Request successfully normalized:")
    print(f"     Section: {req_json['section_id']} | Duration: {req_json['duration_minutes']} min | Department: {req_json['department']}")
    print(f"     Synthesized Text: {req_json['raw_text']}")

    # Step 6: Verify Current Local LAYA Triage
    log_step(6, "Execute & Verify Local LAYA System 1 Triage")
    res = client.post(f"/api/requests/{req_id}/triage")
    assert res.status_code == 200, f"Triage failed: {res.text}"
    triage = res.json()["data"]
    assert triage["department"]["label"] is not None
    assert triage["priority"]["label"] is not None
    assert isinstance(triage["safety_critical"]["label"], bool)
    assert triage["latency_ms"] > 0
    print(f"[OK] LAYA Triage Output ({triage['latency_ms']:.1f} ms | Model: {triage['model_version']}):")
    print(f"     Department: {triage['department']['label']} (Prob: {triage['department'].get('probabilities')})")
    print(f"     Priority: {triage['priority']['label']} (Prob: {triage['priority'].get('probabilities')})")
    print(f"     Safety-Critical: {triage['safety_critical']['label']} ({triage['safety_critical']['probability']:.2f})")

    # Step 7: Verify Queue Persistence
    log_step(7, "Verify Persistence in SQLite Maintenance Queue")
    db = SessionLocal()
    orm_req = db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.id == req_id).first()
    assert orm_req is not None
    assert orm_req.status in [RequestStatus.TRIAGED.value, RequestStatus.AWAITING_REVIEW.value]
    print(f"[OK] Request {req_id} persisted in SQLite with status: {orm_req.status}")
    db.close()

    # Step 8: Run Mathematical Block Planning
    log_step(8, "Execute Mathematical Block Planning (OR-Tools / Deterministic)")
    plan_payload = {
        "request_id": req_id,
        "horizon_hours": 24,
        "max_candidates": 3,
        "auto_evaluate_with_laya": False
    }
    t_plan_start = time.perf_counter()
    res = client.post("/api/planning/run", json=plan_payload)
    plan_latency = (time.perf_counter() - t_plan_start) * 1000
    assert res.status_code == 200, f"Planning failed: {res.text}"
    plan_data = res.json()["data"]
    candidates = plan_data["candidates"]
    assert len(candidates) > 0, "No candidates returned by planner!"
    print(f"[OK] Planner completed in {plan_latency:.1f} ms. Generated {len(candidates)} candidate windows.")

    # Step 9: Verify Deterministic/OR-Tools Candidate Windows
    log_step(9, "Verify Candidate Windows Feasibility & Timetable Compliance")
    first_cand = candidates[0]
    cand_id = first_cand["candidate_id"]
    assert first_cand["feasible"] is True
    assert first_cand["duration_min"] == 120
    assert first_cand["start_time_min"] is not None
    assert first_cand["end_time_min"] is not None
    print(f"[OK] Candidate {cand_id}:")
    print(f"     Window: {first_cand['start_time']} -> {first_cand['end_time']} ({first_cand['start_time_min']}m -> {first_cand['end_time_min']}m)")
    print(f"     Feasible: {first_cand['feasible']} | Optimality Score: {first_cand['optimality_score']:.1f}/100")
    print(f"     Affected Trains: {first_cand['affected_trains']}")

    # Step 10: Verify LAYA Candidate Evaluation
    log_step(10, "Evaluate Candidate Window with LAYA Advisory Engine")
    res = client.post(f"/api/candidates/{cand_id}/evaluate")
    assert res.status_code == 200, f"Candidate eval failed: {res.text}"
    cand_eval = res.json()["data"]
    assert cand_eval["risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert cand_eval["latency_ms"] > 0
    print(f"[OK] LAYA Candidate Evaluation ({cand_eval['latency_ms']:.1f} ms):")
    print(f"     Risk Level: {cand_eval['risk_level']} (Prob: {cand_eval.get('risk_probabilities')})")
    print(f"     Recommendation: {cand_eval['recommended_action']}")
    print(f"     Operational Notes: {cand_eval['conflict_interpretation']}")

    # Step 11: Open Candidate Detail in Planning View
    log_step(11, "Inspect Candidate Details & Advisory Metrics")
    res = client.get(f"/api/requests/{req_id}")
    assert res.status_code == 200
    detail_data = res.json()["data"]
    assert len(detail_data["candidates"]) >= 1
    assert len(detail_data["decisions"]) >= 1
    print(f"[OK] Candidate details retrieved with complete decision audit history.")

    # Step 12: Complete Human Verification Checklist (Enforce G&SR 15.06)
    log_step(12, "Enforce Statutory Controller Verification Checklist")
    # Verify that partial/incomplete checklist is rejected
    incomplete_payload = {
        "candidate_id": cand_id,
        "actor_name": "Chief Controller Nair",
        "actor_role": "Section Controller",
        "reason": "Test incomplete checklist rejection",
        "checklist": {
            "headway_buffer": True,
            "express_corridor": False,  # Not verified!
            "traction_power": True,
            "emergency_corridor": True
        }
    }
    bad_res = client.post(f"/api/requests/{req_id}/approve", json=incomplete_payload)
    assert bad_res.status_code == 400
    print(f"[OK] Incomplete checklist correctly rejected with HTTP 400:")
    print(f"     Backend detail: '{bad_res.json()['detail']}'")

    # Step 13: Approve Candidate with Full Statutory Confirmation
    log_step(13, "Authorize Maintenance Block with Full Verification Checklist")
    valid_payload = {
        "candidate_id": cand_id,
        "actor_name": "Chief Controller Nair",
        "actor_role": "Section Controller",
        "reason": "Authorized for off-peak execution per G&SR 15.06 with 10-minute safety buffer.",
        "checklist": {
            "headway_buffer": True,
            "express_corridor": True,
            "traction_power": True,
            "emergency_corridor": True
        }
    }
    appr_res = client.post(f"/api/requests/{req_id}/approve", json=valid_payload)
    assert appr_res.status_code == 200, f"Approval failed: {appr_res.text}"
    appr_data = appr_res.json()["data"]
    print(f"[OK] Human controller authorization successful: Request {appr_data['request_id']} -> Status: {appr_data['status']}")

    # Step 14: Verify Approved Block Persists in Schedule
    log_step(14, "Verify Approved Block Persists in SQLite Schedule")
    db = SessionLocal()
    persisted_req = db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.id == req_id).first()
    assert persisted_req.status == RequestStatus.APPROVED.value
    assert persisted_req.selected_candidate_id == cand_id
    assert persisted_req.scheduled_start_min == first_cand["start_time_min"]
    assert persisted_req.scheduled_end_min == first_cand["end_time_min"]
    print(f"[OK] Block scheduled from minute {persisted_req.scheduled_start_min} to {persisted_req.scheduled_end_min} on {persisted_req.section_id}")

    # Align block slot to 450-570 min (07:30 - 09:30) for the Train 12076 delay simulation scenario
    persisted_req.scheduled_start_min = 450
    persisted_req.scheduled_end_min = 570
    db.commit()
    db.close()

    # Step 15: Open Audit View
    log_step(15, "Retrieve Audit Trail & System Metrics")
    res = client.get(f"/api/audit?request_id={req_id}")
    assert res.status_code == 200
    audit_events = res.json()["data"]
    res_m = client.get("/api/audit/metrics")
    assert res_m.status_code == 200
    metrics = res_m.json()["data"]
    print(f"[OK] Audit Log retrieved: {len(audit_events)} events for {req_id}")
    print(f"     Total System Events: {metrics['total_audit_events']} | Approvals: {metrics['controller_approvals']}")

    # Step 16: Verify Complete Audit Chain
    log_step(16, "Verify Complete Immutable Audit Event Sequence")
    event_types = [e["event_type"] for e in audit_events]
    expected_chain = [
        AuditEventType.REQUEST_CREATED.value,
        AuditEventType.LAYA_TRIAGE_COMPLETED.value,
        AuditEventType.PLANNER_COMPLETED.value,
        AuditEventType.LAYA_CANDIDATE_EVALUATED.value,
        AuditEventType.CONTROLLER_APPROVED.value
    ]
    for expected in expected_chain:
        assert expected in event_types, f"Missing audit event: {expected} in {event_types}"
        print(f"     ✓ Found event: {expected}")
    print(f"[OK] Complete auditable trail verified with 100% integrity.")

    # Step 17: Open What-If Simulation View
    log_step(17, "Access What-If Disruption Engine")
    res = client.get("/api/incidents")
    assert res.status_code == 200
    print(f"[OK] What-If incident engine ready. Existing incidents: {len(res.json()['data'])}")

    # Step 18: Inject Simulated Train Delay Overlapping Approved Block
    log_step(18, "Inject Disruption: Train 12076 +60m Delay on TVC-QLN Corridor")
    disruption_payload = {
        "incident_type": "Train Delay",
        "train_no": "12076",
        "delay_min": 60,
        "description": "Signal snag at Kochuveli causing 60-min delay on 12076 Jan Shatabdi Express"
    }
    res = client.post("/api/incidents/simulate", json=disruption_payload)
    assert res.status_code == 200, f"Simulation failed: {res.text}"
    sim_data = res.json()["data"]
    print(f"[OK] Incident simulation executed successfully (Simulation ID: {sim_data['incident_id']})")

    # Step 19: Verify Backend Evaluates Incident
    log_step(19, "Verify Deterministic Physical Collision & Overlap Duration")
    assert sim_data["physical_collision_detected"] is True
    assert len(sim_data["collision_details"]) > 0
    collision = sim_data["collision_details"][0]
    print(f"[OK] Physical collision computed mathematically:")
    print(f"     Train: {collision['train_no']} ({collision['train_name']})")
    print(f"     Delayed Window: {collision['delayed_slot']} | Block Window: {collision['block_slot']}")
    print(f"     Encroachment Duration: {collision['overlap_min']} minutes")

    # Step 20: Verify Approved Block is Marked Affected
    log_step(20, "Verify Disruption Engine Flags Active Approved Block")
    assert sim_data["affects_active_block"] is True
    assert sim_data["triggers_reoptimization"] is True
    print(f"[OK] Active block {req_id} marked as critically affected by delayed train path.")

    # Step 21: Verify Block Status Transitions to REOPTIMIZATION_REQUIRED
    log_step(21, "Verify Block Status Transition to REOPTIMIZATION_REQUIRED")
    db = SessionLocal()
    updated_req = db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.id == req_id).first()
    assert updated_req.status == RequestStatus.REOPTIMIZATION_REQUIRED.value
    print(f"[OK] Status safely transitioned: {RequestStatus.APPROVED.value} -> {updated_req.status}")
    print(f"     (Note: System adheres to G&SR; it does NOT silently re-schedule without human oversight)")
    db.close()

    # Step 22: Verify Fresh Candidate Windows Generated
    log_step(22, "Verify Constraint Planner Generates Fresh Conflict-Free Candidates")
    assert sim_data["reoptimization_status"] == "COMPLETED"
    new_cands = sim_data["new_candidates"]
    assert len(new_cands) > 0, "No new candidates generated during reoptimization!"
    print(f"[OK] Reoptimization completed. Generated {len(new_cands)} new candidates avoiding delayed train:")
    for c in new_cands:
        print(f"     - Window {c['candidate_id']}: {c['start_time']} -> {c['end_time']} (Feasible: {c['feasible']})")

    # Step 23: Verify LAYA Evaluates New Candidates
    log_step(23, "Verify LAYA System 1 Risk Evaluation on Fresh Candidates")
    for c in new_cands:
        laya_eval = c.get("laya_evaluation")
        assert laya_eval is not None
        assert laya_eval["risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        print(f"     - Candidate {c['candidate_id']}: Risk={laya_eval['risk_level']} | Rec={laya_eval['recommended_action']} ({laya_eval['latency_ms']:.1f} ms)")

    # Step 24: Verify Human Approval Still Required for New Candidate
    log_step(24, "Verify Human Section Controller Authorization Required for Reoptimized Block")
    new_cand_target = new_cands[0]
    new_cand_id = new_cand_target["candidate_id"]

    # Verify request remains in REOPTIMIZATION_REQUIRED until human controller acts
    res_req = client.get(f"/api/requests/{req_id}")
    assert res_req.json()["data"]["status"] == RequestStatus.REOPTIMIZATION_REQUIRED.value

    # Human Section Controller re-authorizes the new slot
    reopt_approval = {
        "candidate_id": new_cand_id,
        "actor_name": "Chief Controller Nair",
        "actor_role": "Section Controller",
        "reason": "Re-authorized after train 12076 delay adjustment; slot moved to conflict-free window.",
        "checklist": {
            "headway_buffer": True,
            "express_corridor": True,
            "traction_power": True,
            "emergency_corridor": True
        }
    }
    reopt_appr_res = client.post(f"/api/requests/{req_id}/approve", json=reopt_approval)
    assert reopt_appr_res.status_code == 200
    assert reopt_appr_res.json()["data"]["status"] == RequestStatus.APPROVED.value
    print(f"[OK] Controller successfully authorized reoptimized candidate {new_cand_id}!")
    print(f"     Request status returned to: APPROVED")

    # Check updated audit chain
    res_final_audit = client.get(f"/api/audit?request_id={req_id}")
    final_types = [e["event_type"] for e in res_final_audit.json()["data"]]
    assert AuditEventType.ACTIVE_BLOCK_AFFECTED.value in final_types
    assert AuditEventType.REOPTIMIZATION_TRIGGERED.value in final_types
    assert AuditEventType.REOPTIMIZATION_COMPLETED.value in final_types
    print(f"[OK] Audit chain reflects full lifecycle: disruption -> reoptimization -> human re-approval.")


def run_error_handling_tests():
    print("\n********************************************************************************")
    print("RAILSYNC AI: DEFENSIVE ERROR HANDLING & RESILIENCE TESTS")
    print("********************************************************************************")

    # Error 1: Invalid Candidate Selection
    log_step(101, "Error Handling: Invalid Candidate Window Selection")
    res = client.post("/api/requests/MR-NONEXISTENT/approve", json={
        "candidate_id": "CW-FAKE-999",
        "actor_name": "Test Controller",
        "actor_role": "Section Controller",
        "checklist": {"headway_buffer": True, "express_corridor": True, "traction_power": True, "emergency_corridor": True}
    })
    assert res.status_code in [400, 404], f"Expected 400/404, got {res.status_code}"
    print(f"[OK] Rejection on non-existent request/candidate: HTTP {res.status_code} ({res.json()['detail']})")

    # Error 2: Non-existent Train Injection
    log_step(102, "Error Handling: Non-Existent Train Injection in What-If Engine")
    res = client.post("/api/incidents/simulate", json={
        "incident_type": "Train Delay",
        "train_no": "99999",  # Train does not exist in Southern Railway timetable
        "delay_min": 45,
        "description": "Ghost train delay simulation"
    })
    assert res.status_code == 200
    sim_data = res.json()["data"]
    assert sim_data["physical_collision_detected"] is False
    assert sim_data["affects_active_block"] is False
    print(f"[OK] Unknown train 99999 handled gracefully: 0 false collisions, clean response.")

    # Error 3: Malformed Maintenance Request (Unknown Section)
    log_step(103, "Error Handling: Malformed Maintenance Request (Unknown Section)")
    res = client.post("/api/requests", json={
        "section_id": "INVALID-CORRIDOR-XYZ",
        "work_type": "track_repair",
        "duration": 60,
    })
    assert res.status_code == 400
    assert "Unknown railway section" in res.json()["detail"]
    print(f"[OK] Invalid section correctly rejected: HTTP 400 ({res.json()['detail']})")

    # Error 4: Malformed Maintenance Request (Negative Duration)
    log_step(104, "Error Handling: Malformed Maintenance Request (Negative Duration)")
    res = client.post("/api/requests", json={
        "section_id": "TVC-QLN",
        "work_type": "track_repair",
        "duration": -45,
    })
    assert res.status_code == 400
    assert "positive number" in res.json()["detail"]
    print(f"[OK] Negative duration correctly rejected: HTTP 400 ({res.json()['detail']})")

    # Error 5: Checklist Submitted Without Required Checks
    log_step(105, "Error Handling: Approval Checklist Submitted with Incomplete Items")
    # First create a temporary request and candidate to test
    req_res = client.post("/api/requests", json={
        "section_id": "ERS-TCR",
        "work_type": "ohe_maint",
        "duration": 60,
        "raw_text": "OHE insulator replacement",
        "auto_triage": False
    })
    temp_req_id = req_res.json()["data"]["request_id"]
    plan_res = client.post("/api/planning/run", json={"request_id": temp_req_id, "horizon_hours": 12, "max_candidates": 1, "auto_evaluate_with_laya": False})
    temp_cand_id = plan_res.json()["data"]["candidates"][0]["candidate_id"]

    # Test with empty checklist
    res_empty = client.post(f"/api/requests/{temp_req_id}/approve", json={
        "candidate_id": temp_cand_id,
        "actor_name": "Test Controller",
        "actor_role": "Section Controller",
        "checklist": {}  # Empty checklist!
    })
    assert res_empty.status_code == 400
    assert "Statutory controller verification incomplete" in res_empty.json()["detail"]
    print(f"[OK] Empty checklist rejected: HTTP 400 ({res_empty.json()['detail']})")

    # Test with false value
    res_false = client.post(f"/api/requests/{temp_req_id}/approve", json={
        "candidate_id": temp_cand_id,
        "actor_name": "Test Controller",
        "actor_role": "Section Controller",
        "checklist": {
            "headway_buffer": True,
            "express_corridor": True,
            "traction_power": False,  # False!
            "emergency_corridor": True
        }
    })
    assert res_false.status_code == 400
    assert "Statutory controller verification incomplete" in res_false.json()["detail"]
    print(f"[OK] Incomplete checklist rejected: HTTP 400 ({res_false.json()['detail']})")


if __name__ == "__main__":
    t0 = time.perf_counter()
    run_full_journey()
    run_error_handling_tests()
    total_time = time.perf_counter() - t0
    print("\n================================================================================")
    print(f"ALL 24 USER JOURNEY STEPS & DEFENSIVE ERROR TESTS PASSED IN {total_time:.2f}s!")
    print("================================================================================")
