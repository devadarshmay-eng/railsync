import os
import sys
import json
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from app.main import app
from app.db.database import get_db, init_db, SessionLocal
from app.db.models import AuditEventORM, MaintenanceRequestORM, CandidateWindowORM, HumanActionORM

client = TestClient(app)

def run_e2e_verification():
    print("================================================================")
    print("RAILSYNC AI: END-TO-END HUMAN-IN-THE-LOOP OPERATIONAL VERIFICATION")
    print("================================================================")

    init_db()
    db = SessionLocal()

    # Step 1: Submit Maintenance Request
    print("\n--- STEP 1: Creating Maintenance Request ---")
    req_payload = {
        "section_id": "TVC-QLN",
        "asset_id": "TRK-TVC-01",
        "department": "CIVIL",
        "work_type": "track_repair",
        "priority": "HIGH",
        "duration": 120,
        "raw_text": "Severe rail joint weld defect detected near TVC curve 4B; deep packing required.",
        "input_mode": "preset",
        "auto_triage": False
    }
    res = client.post("/api/requests", json=req_payload)
    assert res.status_code in [200, 201], f"Failed creating request: {res.text}"
    req_data = res.json()["data"]
    req_id = req_data["request_id"]
    print(f"[OK] Created request ID: {req_id} (Status: {req_data['status']})")

    # Step 2: Trigger LAYA Triage
    print("\n--- STEP 2: Executing LAYA Triage ---")
    triage_res = client.post(f"/api/requests/{req_id}/triage")
    assert triage_res.status_code == 200, f"Failed triage: {triage_res.text}"
    triage_data = triage_res.json()["data"]
    print(f"[OK] LAYA Triage: Dept={triage_data['department']['label']}, Priority={triage_data['priority']['label']}, SafetyCritical={triage_data['safety_critical']['label']} ({triage_data['latency_ms']} ms)")

    # Step 3: Run Constraint Planner
    print("\n--- STEP 3: Running Mathematical Constraint Planner ---")
    plan_payload = {
        "request_id": req_id,
        "horizon_hours": 24,
        "max_candidates": 3,
        "auto_evaluate_with_laya": False
    }
    plan_res = client.post("/api/planning/run", json=plan_payload)
    assert plan_res.status_code == 200, f"Failed planning: {plan_res.text}"
    cands = plan_res.json()["data"]["candidates"]
    assert len(cands) > 0, "No candidates generated!"
    target_cand = cands[0]
    cand_id = target_cand["candidate_id"]
    print(f"[OK] Generated {len(cands)} candidates. Selected Candidate: {cand_id} ({target_cand['start_time']} -> {target_cand['end_time']}, Feasible: {target_cand['feasible']})")

    # Step 4: Evaluate Candidate with LAYA
    print("\n--- STEP 4: Evaluating Candidate Window with LAYA ---")
    eval_res = client.post(f"/api/candidates/{cand_id}/evaluate")
    assert eval_res.status_code == 200, f"Failed candidate eval: {eval_res.text}"
    eval_data = eval_res.json()["data"]
    print(f"[OK] LAYA Operational Risk: {eval_data['risk_level']}, Action: {eval_data['recommended_action']} ({eval_data['latency_ms']} ms)")
    print(f"     Interpretation: {eval_data['conflict_interpretation']}")

    # Step 5: Test Statutory Checklist Enforcement
    print("\n--- STEP 5: Testing Statutory Verification Checklist Enforcement ---")
    incomplete_approval = {
        "candidate_id": cand_id,
        "actor_name": "Chief Controller Nair",
        "actor_role": "Section Controller",
        "reason": "Preliminary approval without headway buffer.",
        "checklist": {
            "headway_buffer": False,  # Missing!
            "express_corridor": True,
            "traction_power": True,
            "emergency_corridor": True
        }
    }
    bad_res = client.post(f"/api/requests/{req_id}/approve", json=incomplete_approval)
    assert bad_res.status_code == 400, f"Expected 400 for incomplete checklist, got {bad_res.status_code}"
    print(f"[OK] Incomplete checklist correctly rejected with HTTP 400: {bad_res.json()['detail']}")

    # Step 6: Full Human Controller Approval
    print("\n--- STEP 6: Executing Human Section Controller Approval ---")
    valid_approval = {
        "candidate_id": cand_id,
        "actor_name": "Chief Controller Nair",
        "actor_role": "Section Controller",
        "reason": "Authorized for execution in designated off-peak slot with 10-min safety buffer per G&SR 15.06.",
        "checklist": {
            "headway_buffer": True,
            "express_corridor": True,
            "traction_power": True,
            "emergency_corridor": True
        }
    }
    appr_res = client.post(f"/api/requests/{req_id}/approve", json=valid_approval)
    assert appr_res.status_code == 200, f"Failed approval: {appr_res.text}"
    appr_data = appr_res.json()["data"]
    print(f"[OK] Request {req_id} APPROVED! Status: {appr_data['status']}, Scheduled start: {appr_data.get('start')} min")

    # Step 7: Verify Audit Trail & Metrics
    print("\n--- STEP 7: Inspecting Audit Trail & Metrics ---")
    audit_res = client.get(f"/api/audit?request_id={req_id}")
    assert audit_res.status_code == 200
    events = audit_res.json()["data"]
    event_types = [e["event_type"] for e in events]
    print(f"[OK] Found {len(events)} audit events for {req_id}:")
    for e in events:
        print(f"     - [{e['timestamp']}] {e['event_type']} by {e['actor']} (Latency: {e['latency_ms']} ms)")

    assert "laya_triage_completed" in event_types
    assert "laya_candidate_evaluated" in event_types
    assert "controller_approved" in event_types

    metrics_res = client.get("/api/audit/metrics")
    assert metrics_res.status_code == 200
    m = metrics_res.json()["data"]
    print(f"\n[OK] Operational Metrics Summary:")
    print(f"     - Total Audit Events: {m['total_audit_events']}")
    print(f"     - Controller Approvals: {m['controller_approvals']}")
    print(f"     - Controller Rejections: {m['controller_rejections']}")
    print(f"     - LAYA Inferences: {m['laya_inferences']} (avg {m['avg_laya_latency_ms']} ms)")
    print(f"     - Planner Runs: {m['planner_runs']} (avg {m['avg_planner_latency_ms']} ms)")
    print(f"     - Safety Override Count: {m['safety_override_count']}")

    # Step 8: Persistence across Client Restart / Fresh DB Session
    print("\n--- STEP 8: Verifying SQLite Persistence Across Session Restarts ---")
    db.close()
    
    # Fresh database connection to verify physical SQLite tables
    fresh_db = SessionLocal()
    persisted_req = fresh_db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.id == req_id).first()
    assert persisted_req is not None
    assert persisted_req.status == "APPROVED"
    assert persisted_req.selected_candidate_id == cand_id
    
    persisted_action = fresh_db.query(HumanActionORM).filter(HumanActionORM.request_id == req_id).first()
    assert persisted_action is not None
    assert persisted_action.action == "APPROVED"
    assert persisted_action.actor_name == "Chief Controller Nair"
    chk = json.loads(persisted_action.checklist_json)
    assert chk["headway_buffer"] is True
    assert chk["express_corridor"] is True

    persisted_events = fresh_db.query(AuditEventORM).filter(AuditEventORM.request_id == req_id).all()
    assert len(persisted_events) >= 3
    print(f"[OK] Physical SQLite persistence verified across fresh DB session! {len(persisted_events)} events intact.")
    fresh_db.close()

    print("\n================================================================")
    print("ALL END-TO-END OPERATIONAL CHECKS PASSED WITH 100% SUCCESS!")
    print("================================================================")

if __name__ == "__main__":
    run_e2e_verification()
