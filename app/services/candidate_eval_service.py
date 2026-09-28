import json
from sqlalchemy.orm import Session
from app.adapters.laya import get_laya_adapter
from app.core.audit import log_audit_event
from app.db.models import CandidateWindowORM, MaintenanceRequestORM
from app.domain.constants import AuditEventType, ControllerAction, FeasibilityStatus
from app.domain.models import CandidateWindow, LayaCandidateEvaluation, NormalizedRequest


async def evaluate_candidate_window(
    db: Session,
    candidate_id: str,
    actor: str = "system"
) -> LayaCandidateEvaluation:
    """Executes Second LAYA Decision Point: Operational risk assessment of a candidate window."""
    laya_adapter = get_laya_adapter()

    cand_orm = db.query(CandidateWindowORM).filter(CandidateWindowORM.id == candidate_id).first()
    if not cand_orm:
        raise ValueError(f"Candidate window {candidate_id} not found.")

    req_orm = db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.id == cand_orm.request_id).first()
    if not req_orm:
        raise ValueError(f"Request {cand_orm.request_id} not found.")

    norm_req = NormalizedRequest(
        request_id=req_orm.id,
        section_id=req_orm.section_id,
        raw_text=req_orm.raw_text,
        language=req_orm.language,
        input_mode=req_orm.input_mode, # type: ignore
        preset_type=req_orm.preset_type,
        asset_id=req_orm.asset_id,
        duration_minutes=req_orm.duration_minutes,
        timestamp=req_orm.created_at,
        metadata=json.loads(req_orm.metadata_json or "{}"),
    )

    cand = CandidateWindow(
        candidate_id=cand_orm.id,
        request_id=cand_orm.request_id,
        section_id=cand_orm.section_id,
        start_time_min=cand_orm.start_time_min,
        end_time_min=cand_orm.end_time_min,
        duration_min=cand_orm.duration_min,
        affected_trains=json.loads(cand_orm.affected_trains_json or "[]"),
        conflicts=json.loads(cand_orm.conflicts_json or "[]"),
        feasibility_status=FeasibilityStatus(cand_orm.feasibility_status),
        optimality_score=cand_orm.optimality_score,
        constraint_violations=json.loads(cand_orm.constraint_violations_json or "[]"),
        planner_latency_ms=cand_orm.planner_latency_ms,
    )

    # Contextual operational information
    context = {
        "section_lines": 2,
        "traffic_type": "Mixed Passenger and Freight",
    }

    # Run LAYA Candidate Evaluation
    evaluation = laya_adapter.evaluate_candidate(norm_req, cand, context)

    # Cache evaluation on the candidate record
    cand_orm.laya_evaluation_json = json.dumps(evaluation.model_dump())
    db.commit()

    # Log audit event
    await log_audit_event(
        db=db,
        event_type=AuditEventType.LAYA_CANDIDATE_EVALUATED.value,
        request_id=norm_req.request_id,
        actor=actor,
        input_payload={"candidate_id": cand.candidate_id, "start": cand.start_time_min, "end": cand.end_time_min},
        output_payload=evaluation.model_dump(),
        latency_ms=evaluation.latency_ms,
        model_version=evaluation.model_version,
        decision=f"Risk: {evaluation.risk_level}, Action: {evaluation.recommended_action.value}",
    )

    return evaluation
