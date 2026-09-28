import json
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy.orm import Session
from app.core.audit import log_audit_event
from app.core.safety import verify_advisory_compliance
from app.db.models import CandidateWindowORM, HumanActionORM, MaintenanceRequestORM
from app.domain.constants import AuditEventType, RequestStatus
from app.domain.models import ControllerDecisionPayload


async def approve_maintenance_request(
    db: Session,
    request_id: str,
    payload: ControllerDecisionPayload,
) -> MaintenanceRequestORM:
    """Records human section controller authorization for a maintenance block."""
    verify_advisory_compliance(actor_role=payload.actor_role, action="APPROVE")

    req_orm = db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.id == request_id).first()
    if not req_orm:
        raise ValueError(f"Request {request_id} not found.")

    if not payload.candidate_id:
        raise ValueError("Controller must specify an authorized CandidateWindow ID.")

    cand_orm = db.query(CandidateWindowORM).filter(CandidateWindowORM.id == payload.candidate_id).first()
    if not cand_orm or cand_orm.request_id != request_id:
        raise ValueError(f"Candidate {payload.candidate_id} is not valid for request {request_id}.")

    # Validate controller verification checklist if provided
    if payload.checklist is not None:
        required_keys = ["headway_buffer", "express_corridor", "traction_power", "emergency_corridor"]
        missing_or_false = [k for k in required_keys if not payload.checklist.get(k, False)]
        if missing_or_false:
            raise ValueError(
                f"Statutory controller verification incomplete: mandatory checks ({', '.join(missing_or_false)}) must be confirmed before authorization per G&SR 15.06."
            )

    # Update request state
    req_orm.status = RequestStatus.APPROVED.value
    req_orm.selected_candidate_id = cand_orm.id
    req_orm.scheduled_start_min = cand_orm.start_time_min
    req_orm.scheduled_end_min = cand_orm.end_time_min

    # Record Human Action
    action_orm = HumanActionORM(
        id=f"ACT-{uuid4().hex[:8]}",
        request_id=request_id,
        candidate_id=cand_orm.id,
        actor_name=payload.actor_name,
        actor_role=payload.actor_role,
        action="APPROVED",
        reason=payload.reason or "Authorized by section controller after reviewing LAYA risk and timetable conflicts.",
        checklist_json=json.dumps(payload.checklist or {}),
        timestamp=datetime.now(timezone.utc),
    )
    db.add(action_orm)
    db.commit()
    db.refresh(req_orm)

    # Log Audit Event with structured metadata
    await log_audit_event(
        db=db,
        event_type=AuditEventType.CONTROLLER_APPROVED.value,
        request_id=request_id,
        actor=f"{payload.actor_name} ({payload.actor_role})",
        input_payload={"candidate_id": cand_orm.id, "reason": payload.reason, "checklist": payload.checklist or {}},
        output_payload={"status": req_orm.status, "scheduled_start": req_orm.scheduled_start_min, "scheduled_end": req_orm.scheduled_end_min},
        decision="APPROVED",
    )

    return req_orm


async def reject_maintenance_request(
    db: Session,
    request_id: str,
    payload: ControllerDecisionPayload,
) -> MaintenanceRequestORM:
    """Records human section controller rejection of a maintenance block."""
    verify_advisory_compliance(actor_role=payload.actor_role, action="REJECT")

    req_orm = db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.id == request_id).first()
    if not req_orm:
        raise ValueError(f"Request {request_id} not found.")

    if not payload.reason or not payload.reason.strip():
        raise ValueError("Rejection requires a documented operational reason.")

    req_orm.status = RequestStatus.REJECTED.value

    action_orm = HumanActionORM(
        id=f"ACT-{uuid4().hex[:8]}",
        request_id=request_id,
        candidate_id=payload.candidate_id,
        actor_name=payload.actor_name,
        actor_role=payload.actor_role,
        action="REJECTED",
        reason=payload.reason.strip(),
        checklist_json=json.dumps(payload.checklist or {}),
        timestamp=datetime.now(timezone.utc),
    )
    db.add(action_orm)
    db.commit()
    db.refresh(req_orm)

    await log_audit_event(
        db=db,
        event_type=AuditEventType.CONTROLLER_REJECTED.value,
        request_id=request_id,
        actor=f"{payload.actor_name} ({payload.actor_role})",
        input_payload={"candidate_id": payload.candidate_id, "reason": payload.reason.strip(), "checklist": payload.checklist or {}},
        output_payload={"status": req_orm.status},
        decision="REJECTED",
    )

    return req_orm


async def request_reoptimization(
    db: Session,
    request_id: str,
    payload: ControllerDecisionPayload,
) -> MaintenanceRequestORM:
    """Flags request for reoptimization by planner."""
    req_orm = db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.id == request_id).first()
    if not req_orm:
        raise ValueError(f"Request {request_id} not found.")

    req_orm.status = RequestStatus.REOPTIMIZATION_REQUIRED.value

    action_orm = HumanActionORM(
        id=f"ACT-{uuid4().hex[:8]}",
        request_id=request_id,
        candidate_id=payload.candidate_id,
        actor_name=payload.actor_name,
        actor_role=payload.actor_role,
        action="REOPTIMIZE_REQUESTED",
        reason=payload.reason or "Reoptimization requested by controller.",
        checklist_json=json.dumps(payload.checklist or {}),
        timestamp=datetime.now(timezone.utc),
    )
    db.add(action_orm)
    db.commit()
    db.refresh(req_orm)

    await log_audit_event(
        db=db,
        event_type=AuditEventType.REOPTIMIZATION_TRIGGERED.value,
        request_id=request_id,
        actor=f"{payload.actor_name} ({payload.actor_role})",
        input_payload={"candidate_id": payload.candidate_id, "reason": payload.reason},
        output_payload={"status": req_orm.status},
        decision="REOPTIMIZATION_REQUIRED",
    )

    return req_orm
