import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session
from app.core.audit import log_audit_event
from app.core.safety import get_safety_headers
from app.db.database import get_db
from app.db.models import CandidateWindowORM, LayaDecisionORM, MaintenanceRequestORM
from app.domain.constants import AuditEventType, RequestStatus
from app.domain.models import (
    ControllerDecisionPayload,
    LayaTriageDecision,
    RequestCreatePayload,
)
from app.services.controller_service import (
    approve_maintenance_request,
    reject_maintenance_request,
    request_reoptimization,
)
from app.services.input_normalizer import normalize_request_input
from app.services.planning_service import execute_block_planning
from app.services.candidate_eval_service import evaluate_candidate_window
from app.services.triage_service import execute_request_triage

router = APIRouter(prefix="/api/requests", tags=["Maintenance Requests"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_maintenance_request(
    payload: RequestCreatePayload,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Submit a maintenance request through structured preset button or free text.
    Validates input, creates canonical request record, logs request_created,
    and runs real local LAYA triage (auto_triage=True by default).
    """
    response.headers.update(get_safety_headers())

    try:
        norm_req = normalize_request_input(payload)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err)
        )

    req_orm = MaintenanceRequestORM(
        id=norm_req.request_id,
        section_id=norm_req.section_id,
        raw_text=norm_req.raw_text,
        language=norm_req.language,
        input_mode=norm_req.input_mode,
        preset_type=norm_req.preset_type,
        department=norm_req.department,
        priority=norm_req.priority,
        asset_id=norm_req.asset_id,
        duration_minutes=norm_req.duration_minutes,
        status=RequestStatus.RECEIVED.value,
        metadata_json=json.dumps(norm_req.metadata),
    )
    db.add(req_orm)
    db.commit()
    db.refresh(req_orm)

    # 1. Audit: request_created
    await log_audit_event(
        db=db,
        event_type=AuditEventType.REQUEST_CREATED.value,
        request_id=req_orm.id,
        actor="Section Controller / Engineer",
        input_payload=payload.model_dump(),
        output_payload={"request_id": req_orm.id, "status": req_orm.status, "section": req_orm.section_id},
        decision="REQUEST_CREATED",
    )

    triage_data = None
    # 2. Automatic LAYA Triage if enabled
    if payload.auto_triage:
        try:
            triage_decision: LayaTriageDecision = await execute_request_triage(
                db=db,
                request_orm=req_orm,
                actor="Controller / Engineer (Auto-Triage)"
            )
            triage_data = triage_decision.model_dump()
        except Exception as exc:
            # If LAYA fails, the request remains in RECEIVED status with error details
            return {
                "status": "partial_success",
                "message": f"Request created, but LAYA triage failed: {exc}",
                "data": {
                    "request_id": req_orm.id,
                    "section_id": req_orm.section_id,
                    "raw_text": req_orm.raw_text,
                    "status": req_orm.status,
                    "duration_minutes": req_orm.duration_minutes,
                    "created_at": req_orm.created_at.isoformat(),
                    "triage": None,
                    "triage_error": str(exc),
                }
            }

    return {
        "status": "success",
        "data": {
            "request_id": req_orm.id,
            "section_id": req_orm.section_id,
            "raw_text": req_orm.raw_text,
            "status": req_orm.status,
            "input_mode": req_orm.input_mode,
            "language": req_orm.language,
            "department": req_orm.department,
            "priority": req_orm.priority,
            "asset_id": req_orm.asset_id,
            "duration_minutes": req_orm.duration_minutes,
            "created_at": req_orm.created_at.isoformat(),
            "triage": triage_data,
        }
    }


@router.post("/{request_id}/triage")
async def triage_maintenance_request(
    request_id: str,
    response: Response,
    db: Session = Depends(get_db),
):
    """Trigger LAYA Decision Engine for structured request triage."""
    response.headers.update(get_safety_headers())
    req_orm = db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.id == request_id).first()
    if not req_orm:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found.")

    try:
        decision: LayaTriageDecision = await execute_request_triage(
            db=db,
            request_orm=req_orm,
            actor="Section Controller (Manual Trigger)"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LAYA Decision Engine unavailable: {exc}"
        )

    return {"status": "success", "data": decision.model_dump()}


@router.get("")
def list_maintenance_requests(
    response: Response,
    status_filter: Optional[str] = Query(None, alias="status"),
    section_id: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    limit: int = Query(100, le=200),
    db: Session = Depends(get_db),
):
    """List requests in the maintenance queue with optional status/section/department filtering."""
    response.headers.update(get_safety_headers())
    query = db.query(MaintenanceRequestORM)
    if status_filter:
        query = query.filter(MaintenanceRequestORM.status == status_filter.upper())
    if section_id:
        query = query.filter(MaintenanceRequestORM.section_id == section_id)
    if department:
        query = query.filter(MaintenanceRequestORM.department == department)

    records = query.order_by(MaintenanceRequestORM.created_at.desc()).limit(limit).all()

    items = []
    for r in records:
        latest_decision = db.query(LayaDecisionORM).filter(
            LayaDecisionORM.request_id == r.id,
            LayaDecisionORM.decision_point == "TRIAGE"
        ).order_by(LayaDecisionORM.created_at.desc()).first()

        dept_probs = None
        prio_probs = None
        if latest_decision:
            if latest_decision.department_probs:
                dept_probs = json.loads(latest_decision.department_probs)
            if latest_decision.priority_probs:
                prio_probs = json.loads(latest_decision.priority_probs)

        items.append({
            "id": r.id,
            "section_id": r.section_id,
            "raw_text": r.raw_text,
            "status": r.status,
            "input_mode": r.input_mode,
            "language": r.language,
            "metadata": json.loads(r.metadata_json) if r.metadata_json else {},
            "preset_type": r.preset_type,
            "department": r.department or (latest_decision.department if latest_decision else None),
            "priority": r.priority or (latest_decision.priority if latest_decision else None),
            "asset_id": r.asset_id,
            "duration_minutes": r.duration_minutes,
            "scheduled_start_min": r.scheduled_start_min,
            "scheduled_end_min": r.scheduled_end_min,
            "created_at": r.created_at.isoformat(),
            "triage": {
                "department": {
                    "label": latest_decision.department,
                    "probabilities": dept_probs,
                },
                "priority": {
                    "label": latest_decision.priority,
                    "probabilities": prio_probs,
                },
                "safety_critical": {
                    "label": latest_decision.safety_critical,
                    "probability": latest_decision.safety_critical_prob,
                },
                "confidence": latest_decision.confidence,
                "latency_ms": latest_decision.latency_ms,
                "model_version": latest_decision.model_version,
            } if latest_decision else None
        })

    return {"status": "success", "count": len(items), "data": items}


@router.get("/{request_id}")
def get_maintenance_request(
    request_id: str,
    response: Response,
    db: Session = Depends(get_db),
):
    """Fetch complete request details, triage distributions, candidates, and human actions."""
    response.headers.update(get_safety_headers())
    req_orm = db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.id == request_id).first()
    if not req_orm:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found.")

    decisions = db.query(LayaDecisionORM).filter(LayaDecisionORM.request_id == request_id).all()
    candidates = db.query(CandidateWindowORM).filter(CandidateWindowORM.request_id == request_id).all()

    return {
        "status": "success",
        "data": {
            "id": req_orm.id,
            "section_id": req_orm.section_id,
            "raw_text": req_orm.raw_text,
            "status": req_orm.status,
            "input_mode": req_orm.input_mode,
            "language": req_orm.language,
            "metadata": json.loads(req_orm.metadata_json) if req_orm.metadata_json else {},
            "preset_type": req_orm.preset_type,
            "department": req_orm.department,
            "priority": req_orm.priority,
            "asset_id": req_orm.asset_id,
            "duration_minutes": req_orm.duration_minutes,
            "scheduled_start_min": req_orm.scheduled_start_min,
            "scheduled_end_min": req_orm.scheduled_end_min,
            "selected_candidate_id": req_orm.selected_candidate_id,
            "created_at": req_orm.created_at.isoformat(),
            "decisions": [
                {
                    "id": d.id,
                    "decision_point": d.decision_point,
                    "department": d.department,
                    "department_probs": json.loads(d.department_probs) if d.department_probs else None,
                    "priority": d.priority,
                    "priority_probs": json.loads(d.priority_probs) if d.priority_probs else None,
                    "safety_critical": d.safety_critical,
                    "safety_critical_prob": d.safety_critical_prob,
                    "confidence": d.confidence,
                    "latency_ms": d.latency_ms,
                    "model_version": d.model_version,
                }
                for d in decisions
            ],
            "candidates": [
                {
                    "id": c.id,
                    "start_time_min": c.start_time_min,
                    "end_time_min": c.end_time_min,
                    "affected_trains": json.loads(c.affected_trains_json or "[]"),
                    "conflicts": json.loads(c.conflicts_json or "[]"),
                    "feasibility_status": c.feasibility_status,
                    "optimality_score": c.optimality_score,
                    "laya_evaluation": json.loads(c.laya_evaluation_json) if c.laya_evaluation_json else None,
                }
                for c in candidates
            ]
        }
    }


@router.post("/{request_id}/approve")
async def approve_request_endpoint(
    request_id: str,
    payload: ControllerDecisionPayload,
    response: Response,
    db: Session = Depends(get_db),
):
    """Section Controller advisory approval of a candidate maintenance window."""
    response.headers.update(get_safety_headers())
    try:
        updated = await approve_maintenance_request(db=db, request_id=request_id, payload=payload)
        return {
            "status": "success",
            "message": f"Block authorized by {payload.actor_name}",
            "data": {"request_id": updated.id, "status": updated.status, "start": updated.scheduled_start_min}
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{request_id}/reject")
async def reject_request_endpoint(
    request_id: str,
    payload: ControllerDecisionPayload,
    response: Response,
    db: Session = Depends(get_db),
):
    """Section Controller rejection of a maintenance block proposal."""
    response.headers.update(get_safety_headers())
    try:
        updated = await reject_maintenance_request(db=db, request_id=request_id, payload=payload)
        return {"status": "success", "message": "Request rejected", "data": {"request_id": updated.id, "status": updated.status}}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{request_id}/reoptimize")
async def reoptimize_request_endpoint(
    request_id: str,
    payload: ControllerDecisionPayload,
    response: Response,
    db: Session = Depends(get_db),
):
    """Section Controller request for planner reoptimization."""
    response.headers.update(get_safety_headers())
    try:
        updated = await request_reoptimization(db=db, request_id=request_id, payload=payload)
        
        # Execute the real mathematical block planner again
        new_candidates = await execute_block_planning(
            db=db,
            request_orm=updated,
            horizon_hours=48,
            max_candidates=5,
        )

        # Re-evaluate generated candidate windows with LAYA
        for cand in new_candidates:
            try:
                eval_res = await evaluate_candidate_window(
                    db=db,
                    candidate_id=cand.candidate_id,
                    actor=f"{payload.actor_name} ({payload.actor_role})",
                )
                cand.laya_evaluation = eval_res.model_dump()
            except Exception:
                pass

        return {
            "status": "success",
            "message": f"Reoptimization complete: generated {len(new_candidates)} fresh candidates using constraint planner",
            "data": {
                "request_id": updated.id,
                "status": updated.status,
                "candidate_count": len(new_candidates),
                "candidates": [c.model_dump() for c in new_candidates],
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
