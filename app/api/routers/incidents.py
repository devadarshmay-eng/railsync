from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from app.core.safety import get_safety_headers
from app.db.database import get_db
from app.db.models import IncidentORM
from app.domain.models import (
    DisruptionSimulationResult,
    IncidentSimulationPayload,
)
from app.services.incident_service import simulate_and_evaluate_incident

router = APIRouter(prefix="/api/incidents", tags=["What-If Incident Engine"])


@router.post("/simulate")
async def simulate_incident_endpoint(
    payload: IncidentSimulationPayload,
    response: Response,
    db: Session = Depends(get_db),
):
    """Simulate an incident (train delay, signal failure, track defect, OHE breakdown) and evaluate reoptimization via LAYA."""
    response.headers.update(get_safety_headers())
    result: DisruptionSimulationResult = await simulate_and_evaluate_incident(
        db=db,
        payload=payload,
        actor="Simulation Controller",
    )
    return {"status": "success", "data": result.model_dump()}


@router.post("")
async def commit_actual_incident_endpoint(
    payload: IncidentSimulationPayload,
    response: Response,
    db: Session = Depends(get_db),
):
    """Report an actual incident on the railway corridor and trigger reoptimization if required."""
    response.headers.update(get_safety_headers())
    result: DisruptionSimulationResult = await simulate_and_evaluate_incident(
        db=db,
        payload=payload,
        actor="Field Controller / Section Master",
    )
    return {"status": "success", "data": result.model_dump()}


@router.get("")
def list_incidents(
    response: Response,
    section_id: Optional[str] = Query(None),
    limit: int = Query(20, le=50),
    db: Session = Depends(get_db),
):
    """Retrieve logged incidents and simulation runs."""
    response.headers.update(get_safety_headers())
    query = db.query(IncidentORM)
    if section_id:
        query = query.filter(IncidentORM.section_id == section_id)
    records = query.order_by(IncidentORM.created_at.desc()).limit(limit).all()

    return {
        "status": "success",
        "data": [
            {
                "id": r.id,
                "incident_type": r.incident_type,
                "section_id": r.section_id,
                "train_no": r.train_no,
                "delay_min": r.delay_min,
                "description": r.description,
                "severity": r.severity,
                "affects_active_block": r.affects_active_block,
                "triggers_reoptimization": r.triggers_reoptimization,
                "confidence": r.laya_confidence,
                "latency_ms": r.latency_ms,
                "created_at": r.created_at.isoformat(),
            }
            for r in records
        ]
    }
