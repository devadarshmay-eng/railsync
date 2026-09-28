import json
import time
from typing import List, Optional
from uuid import uuid4
from sqlalchemy.orm import Session
from app.adapters.planner import get_block_planner
from app.core.audit import log_audit_event
from app.db.models import CandidateWindowORM, MaintenanceRequestORM, PlanningRunORM
from app.db.seed import TRAIN_TIMETABLE
from app.domain.constants import AuditEventType, RequestStatus
from app.domain.models import CandidateWindow, NormalizedRequest, TrainModel


async def execute_block_planning(
    db: Session,
    request_orm: MaintenanceRequestORM,
    horizon_hours: int = 48,
    max_candidates: int = 5,
    actor: str = "system",
    timetable: Optional[List[TrainModel]] = None,
) -> List[CandidateWindow]:
    """Runs deterministic / OR-Tools CP-SAT block planning to generate feasible candidate maintenance windows."""
    t_start = time.perf_counter()
    planner = get_block_planner()

    # Reconstruct normalized request
    norm_req = NormalizedRequest(
        request_id=request_orm.id,
        section=request_orm.section_id,
        section_id=request_orm.section_id,
        raw_text=request_orm.raw_text,
        language=request_orm.language,
        input_mode=request_orm.input_mode, # type: ignore
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

    # 1. Log Planner Started
    await log_audit_event(
        db=db,
        event_type=AuditEventType.PLANNER_STARTED.value,
        request_id=request_orm.id,
        actor=actor,
        input_payload={"section_id": norm_req.section_id, "duration": norm_req.duration_minutes},
    )

    # 2. Gather existing active / approved blocks from DB
    active_requests = db.query(MaintenanceRequestORM).filter(
        MaintenanceRequestORM.status.in_([RequestStatus.APPROVED.value]),
        MaintenanceRequestORM.scheduled_start_min.isnot(None),
    ).all()

    existing_blocks = [
        {
            "candidate_id": r.selected_candidate_id,
            "section_id": r.section_id,
            "asset_id": r.asset_id,
            "start_time_min": r.scheduled_start_min,
            "end_time_min": r.scheduled_end_min,
            "blocks_section": True,
        }
        for r in active_requests
    ]

    # 3. Generate candidate windows using active planner
    candidates = planner.plan_candidate_windows(
        request=norm_req,
        timetable=timetable if timetable is not None else TRAIN_TIMETABLE,
        existing_blocks=existing_blocks,
        horizon_minutes=horizon_hours * 60,
        max_candidates=max_candidates,
    )

    total_latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

    # 4. Save PlanningRun record
    plan_run_id = f"PLN-{uuid4().hex[:8]}"
    planning_run = PlanningRunORM(
        id=plan_run_id,
        request_id=request_orm.id,
        solver_type=planner.get_solver_name(),
        status="COMPLETED",
        latency_ms=total_latency_ms,
    )
    db.add(planning_run)

    # 5. Clear previous candidates for this request and insert new ones
    db.query(CandidateWindowORM).filter(CandidateWindowORM.request_id == request_orm.id).delete()

    for cand in candidates:
        cand_orm = CandidateWindowORM(
            id=cand.candidate_id,
            planning_run_id=plan_run_id,
            request_id=request_orm.id,
            section_id=cand.section_id,
            start_time_min=cand.start_time_min,
            end_time_min=cand.end_time_min,
            duration_min=cand.duration_min,
            affected_trains_json=json.dumps(cand.affected_trains),
            conflicts_json=json.dumps(cand.conflicts),
            feasibility_status=cand.feasibility_status.value,
            optimality_score=cand.optimality_score,
            constraint_violations_json=json.dumps(cand.constraint_violations),
            planner_latency_ms=cand.planner_latency_ms,
        )
        db.add(cand_orm)

    request_orm.status = RequestStatus.AWAITING_REVIEW.value
    db.commit()
    db.refresh(request_orm)

    # 6. Log Planner Completed
    await log_audit_event(
        db=db,
        event_type=AuditEventType.PLANNER_COMPLETED.value,
        request_id=request_orm.id,
        actor=actor,
        output_payload={"candidate_count": len(candidates), "solver": planner.get_solver_name()},
        latency_ms=total_latency_ms,
        decision=f"Generated {len(candidates)} candidate windows",
    )

    return candidates
