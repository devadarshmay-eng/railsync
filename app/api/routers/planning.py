import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.safety import get_safety_headers
from app.db.database import get_db
from app.db.models import CandidateWindowORM, MaintenanceRequestORM, PlanningRunORM
from app.domain.models import CandidateWindow
from app.services.candidate_eval_service import evaluate_candidate_window
from app.services.planning_service import execute_block_planning

router = APIRouter(prefix="/api/planning", tags=["Block Planning"])


class PlanningRunPayload(BaseModel):
    request_id: str
    horizon_hours: Optional[int] = 48
    max_candidates: Optional[int] = 5
    auto_evaluate_with_laya: Optional[bool] = True


@router.post("/run")
async def run_planning_engine(
    payload: PlanningRunPayload,
    response: Response,
    db: Session = Depends(get_db),
):
    """Run deterministic / OR-Tools CP-SAT block planning to generate feasible candidate windows."""
    response.headers.update(get_safety_headers())
    req_orm = db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.id == payload.request_id).first()
    if not req_orm:
        raise HTTPException(status_code=404, detail=f"Request {payload.request_id} not found.")

    candidates = await execute_block_planning(
        db=db,
        request_orm=req_orm,
        horizon_hours=payload.horizon_hours or 48,
        max_candidates=payload.max_candidates or 5,
    )

    # Optional immediate evaluation of top candidate with LAYA (Second Decision Point)
    if payload.auto_evaluate_with_laya:
        for cand in candidates:
            try:
                eval_res = await evaluate_candidate_window(db=db, candidate_id=cand.candidate_id)
                cand.laya_evaluation = eval_res.model_dump()
            except Exception:
                pass

    return {
        "status": "success",
        "data": {
            "request_id": req_orm.id,
            "candidate_count": len(candidates),
            "candidates": [c.model_dump() for c in candidates],
        }
    }


@router.get("/{request_id}")
def get_candidate_windows_for_request(
    request_id: str,
    response: Response,
    db: Session = Depends(get_db),
):
    """Retrieve all candidate windows generated for a maintenance request."""
    response.headers.update(get_safety_headers())
    cands = db.query(CandidateWindowORM).filter(CandidateWindowORM.request_id == request_id).all()
    if not cands:
        raise HTTPException(status_code=404, detail=f"No candidates found for request {request_id}.")

    latest_run = db.query(PlanningRunORM).filter(PlanningRunORM.request_id == request_id).order_by(PlanningRunORM.created_at.desc()).first()

    return {
        "status": "success",
        "data": {
            "request_id": request_id,
            "planning_run": {
                "id": latest_run.id if latest_run else None,
                "solver": latest_run.solver_type if latest_run else None,
                "latency_ms": latest_run.latency_ms if latest_run else None,
            },
            "candidates": [
                CandidateWindow(
                    candidate_id=c.id,
                    request_id=c.request_id,
                    section=c.section_id,
                    section_id=c.section_id,
                    start_time_min=c.start_time_min,
                    end_time_min=c.end_time_min,
                    duration_min=c.duration_min,
                    duration=c.duration_min,
                    affected_trains=json.loads(c.affected_trains_json or "[]"),
                    conflicts=json.loads(c.conflicts_json or "[]"),
                    feasibility_status=c.feasibility_status,
                    optimality_score=c.optimality_score,
                    constraint_violations=json.loads(c.constraint_violations_json or "[]"),
                    planner_version=latest_run.solver_type if latest_run else "DeterministicConstraintPlanner@1.0",
                    planner_latency_ms=c.planner_latency_ms,
                    laya_evaluation=json.loads(c.laya_evaluation_json) if c.laya_evaluation_json else None,
                ).model_dump()
                for c in cands
            ]
        }
    }
