import json
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.safety import get_safety_headers
from app.db.database import get_db
from app.db.models import AuditEventORM
from app.domain.constants import AuditEventType

router = APIRouter(prefix="/api/audit", tags=["Audit Trail & Telemetry"])


@router.get("/metrics")
def get_audit_metrics(
    response: Response,
    db: Session = Depends(get_db),
):
    """Computes genuine audit metrics directly from database state (no fabricated metrics)."""
    response.headers.update(get_safety_headers())
    total_events = db.query(AuditEventORM).count()
    approvals = db.query(AuditEventORM).filter(AuditEventORM.event_type == AuditEventType.CONTROLLER_APPROVED.value).count()
    rejections = db.query(AuditEventORM).filter(AuditEventORM.event_type == AuditEventType.CONTROLLER_REJECTED.value).count()
    reoptimizations = db.query(AuditEventORM).filter(AuditEventORM.event_type == AuditEventType.REOPTIMIZATION_TRIGGERED.value).count()
    triage_runs = db.query(AuditEventORM).filter(AuditEventORM.event_type == AuditEventType.LAYA_TRIAGE_COMPLETED.value).count()
    eval_runs = db.query(AuditEventORM).filter(AuditEventORM.event_type == AuditEventType.LAYA_CANDIDATE_EVALUATED.value).count()
    planner_runs = db.query(AuditEventORM).filter(AuditEventORM.event_type == AuditEventType.PLANNER_COMPLETED.value).count()

    avg_laya_lat = db.query(func.avg(AuditEventORM.latency_ms)).filter(
        AuditEventORM.event_type.in_([AuditEventType.LAYA_TRIAGE_COMPLETED.value, AuditEventType.LAYA_CANDIDATE_EVALUATED.value]),
        AuditEventORM.latency_ms.isnot(None)
    ).scalar() or 0.0

    avg_planner_lat = db.query(func.avg(AuditEventORM.latency_ms)).filter(
        AuditEventORM.event_type == AuditEventType.PLANNER_COMPLETED.value,
        AuditEventORM.latency_ms.isnot(None)
    ).scalar() or 0.0

    return {
        "status": "success",
        "data": {
            "total_audit_events": total_events,
            "controller_approvals": approvals,
            "controller_rejections": rejections,
            "reoptimizations_triggered": reoptimizations,
            "laya_inferences": triage_runs + eval_runs,
            "planner_runs": planner_runs,
            "avg_laya_latency_ms": round(float(avg_laya_lat), 1),
            "avg_planner_latency_ms": round(float(avg_planner_lat), 1),
            "uptime": "DEMO METRIC (Local Prototype)",
            "safety_override_count": "0 (Autonomous override prohibited by G&SR)",
        }
    }


@router.get("")
def get_audit_trail(
    response: Response,
    event_type: Optional[str] = Query(None),
    request_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """Retrieve immutable audit log events across triage, planning, LAYA evaluation, and controller actions."""
    response.headers.update(get_safety_headers())
    query = db.query(AuditEventORM)

    if event_type:
        query = query.filter(AuditEventORM.event_type == event_type)
    if request_id:
        query = query.filter(AuditEventORM.request_id == request_id)

    records = query.order_by(AuditEventORM.timestamp.desc()).limit(limit).all()

    return {
        "status": "success",
        "count": len(records),
        "data": [
            {
                "id": r.id,
                "event_type": r.event_type,
                "request_id": r.request_id,
                "actor": r.actor,
                "input": json.loads(r.input_payload or "{}"),
                "output": json.loads(r.output_payload or "{}"),
                "model_version": r.model_version,
                "latency_ms": r.latency_ms,
                "decision": r.decision,
                "metadata": json.loads(r.metadata_json or "{}"),
                "timestamp": r.timestamp.isoformat(),
            }
            for r in records
        ]
    }
