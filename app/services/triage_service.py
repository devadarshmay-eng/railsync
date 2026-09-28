import json
from uuid import uuid4
from sqlalchemy.orm import Session
from app.adapters.laya import get_laya_adapter
from app.core.audit import log_audit_event
from app.core.events import broadcaster
from app.db.models import LayaDecisionORM, MaintenanceRequestORM
from app.domain.constants import AuditEventType, RequestStatus
from app.domain.models import LayaTriageDecision, NormalizedRequest


async def execute_request_triage(
    db: Session,
    request_orm: MaintenanceRequestORM,
    actor: str = "system"
) -> LayaTriageDecision:
    """
    Invokes LAYA Decision Engine (Decision Point 1: Request Triage).
    Logs laya_triage_started, runs real LAYA forward pass with measured latency,
    persists decision and true probabilities, updates request status to TRIAGED,
    and logs laya_triage_completed.
    """
    laya_adapter = get_laya_adapter()
    
    # 1. Reconstruct canonical normalized request
    norm_req = NormalizedRequest(
        request_id=request_orm.id,
        section=request_orm.section_id,
        section_id=request_orm.section_id,
        raw_text=request_orm.raw_text,
        language=request_orm.language,
        input_mode=request_orm.input_mode,  # type: ignore
        preset_type=request_orm.preset_type,
        maintenance_type=request_orm.preset_type,
        department=request_orm.department,
        priority=request_orm.priority,
        asset_id=request_orm.asset_id,
        duration=request_orm.duration_minutes,
        duration_minutes=request_orm.duration_minutes,
        timestamp=request_orm.created_at,
        metadata=json.loads(request_orm.metadata_json or "{}"),
    )

    # 2. Audit: laya_triage_started
    await log_audit_event(
        db=db,
        event_type=AuditEventType.LAYA_TRIAGE_STARTED.value,
        request_id=request_orm.id,
        actor=actor,
        input_payload={
            "request_id": norm_req.request_id,
            "section": norm_req.section,
            "raw_text": norm_req.raw_text,
            "input_mode": norm_req.input_mode,
            "preset_type": norm_req.preset_type,
            "duration": norm_req.duration,
        },
        decision="TRIAGE_STARTED",
        metadata={
            "department_hint": norm_req.department,
            "priority_hint": norm_req.priority,
        },
    )

    # 3. Execute LAYA System 1 forward pass
    try:
        triage_result = laya_adapter.triage_request(norm_req)
    except Exception as exc:
        await log_audit_event(
            db=db,
            event_type="laya_triage_failed",
            request_id=request_orm.id,
            actor=actor,
            input_payload={"raw_text": norm_req.raw_text},
            output_payload={"error": str(exc)},
            decision="TRIAGE_FAILED",
            metadata={"error": str(exc)},
        )
        raise exc

    # 4. Store LAYA decision record in SQLite
    dept_label = triage_result.department.label
    prio_label = triage_result.priority.label
    dept_probs_json = (
        json.dumps(triage_result.department.probabilities)
        if triage_result.department.probabilities is not None
        else None
    )
    prio_probs_json = (
        json.dumps(triage_result.priority.probabilities)
        if triage_result.priority.probabilities is not None
        else None
    )

    conf_score = 1.0
    if triage_result.department.probabilities:
        conf_score = triage_result.department.probabilities.get(dept_label, 0.8)

    decision_orm = LayaDecisionORM(
        id=f"DEC-{uuid4().hex[:8]}",
        request_id=request_orm.id,
        decision_point="TRIAGE",
        department=dept_label,
        department_probs=dept_probs_json,
        priority=prio_label,
        priority_probs=prio_probs_json,
        safety_critical=triage_result.safety_critical.label,
        safety_critical_prob=triage_result.safety_critical.probability,
        confidence=conf_score,
        latency_ms=triage_result.latency_ms,
        model_version=triage_result.model_version,
    )
    db.add(decision_orm)

    # 5. Update request status to TRIAGED and enrich with LAYA classifications
    request_orm.status = RequestStatus.TRIAGED.value
    request_orm.department = dept_label
    request_orm.priority = prio_label
    db.commit()
    db.refresh(request_orm)

    # 6. Audit: laya_triage_completed
    await log_audit_event(
        db=db,
        event_type=AuditEventType.LAYA_TRIAGE_COMPLETED.value,
        request_id=request_orm.id,
        actor=actor,
        input_payload={"raw_text": norm_req.raw_text, "section_id": norm_req.section_id},
        output_payload=triage_result.model_dump(),
        latency_ms=triage_result.latency_ms,
        model_version=triage_result.model_version,
        decision=f"Dept: {dept_label}, Prio: {prio_label}, SafetyCritical: {triage_result.safety_critical.label}",
        metadata={"probabilities_available": triage_result.probabilities_available},
    )

    # 7. Broadcast live SSE notification
    await broadcaster.broadcast("laya_triage_completed", {
        "request_id": request_orm.id,
        "department": dept_label,
        "priority": prio_label,
        "safety_critical": triage_result.safety_critical.label,
        "latency_ms": triage_result.latency_ms,
        "model_version": triage_result.model_version,
    })

    return triage_result
