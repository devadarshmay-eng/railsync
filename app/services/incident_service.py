import json
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4
from sqlalchemy.orm import Session
from app.adapters.laya import get_laya_adapter
from app.core.audit import log_audit_event
from app.core.events import broadcaster
from app.db.models import IncidentORM, MaintenanceRequestORM
from app.db.seed import TRAIN_TIMETABLE
from app.domain.constants import AuditEventType, IncidentType, RequestStatus
from app.domain.models import (
    CandidateWindow,
    DisruptionSimulationResult,
    IncidentEvaluationDecision,
    IncidentSimulationPayload,
    SectionOccupancy,
    TrainModel,
)
from app.services.candidate_eval_service import evaluate_candidate_window
from app.services.planning_service import execute_block_planning


def sections_match(s1: str, s2: str) -> bool:
    """Checks whether two section identifiers match directly or in reverse (up/down lines)."""
    if not s1 or not s2:
        return False
    if s1 == s2:
        return True
    p1 = s1.split("-")
    p2 = s2.split("-")
    if len(p1) == 2 and len(p2) == 2:
        return (p1[0] == p2[1] and p1[1] == p2[0])
    return False


async def simulate_and_evaluate_incident(
    db: Session,
    payload: IncidentSimulationPayload,
    actor: str = "Simulation Controller"
) -> DisruptionSimulationResult:
    """
    Evaluates an incident through deterministic timetable collision calculation
    and LAYA advisory decision engine.
    
    If physical collision with an approved block is detected:
    - Transitions affected approved block to REOPTIMIZATION_REQUIRED
    - Triggers physical constraint planner with delayed train timetable
    - Evaluates freshly generated candidate windows with LAYA
    - Logs audit events: incident_created, incident_evaluated, active_block_affected,
      reoptimization_triggered, reoptimization_completed
    - Never auto-approves: leaves new candidates ready for human Section Controller review.
    
    If no collision:
    - Logs incident_created, incident_evaluated, reoptimization_not_required.
    """
    t_start = time.perf_counter()
    delay_min = int(payload.expected_delay_min or payload.delay_min or 30)

    # 1. Audit: incident_created
    await log_audit_event(
        db=db,
        event_type=AuditEventType.INCIDENT_CREATED.value,
        actor=actor,
        input_payload=payload.model_dump(),
        metadata={
            "incident_type": payload.incident_type.value,
            "train_no": payload.train_no,
            "delay_min": delay_min,
            "section_id": payload.section_id,
        },
    )

    # 2. Locate train in timetable
    target_train: Optional[TrainModel] = None
    if payload.train_no:
        for t in TRAIN_TIMETABLE:
            if t.no == payload.train_no:
                target_train = t
                break

    # Determine default section if omitted
    target_section_id = payload.section_id
    if not target_section_id:
        if target_train and target_train.occupancies:
            target_section_id = target_train.occupancies[0].section_id
        else:
            target_section_id = "ERS-TCR"

    # 3. Query all approved or scheduled blocks from DB
    approved_requests = db.query(MaintenanceRequestORM).filter(
        MaintenanceRequestORM.status.in_([RequestStatus.APPROVED.value, RequestStatus.AWAITING_REVIEW.value]),
        MaintenanceRequestORM.scheduled_start_min.isnot(None),
    ).all()

    # 4. Deterministic Timetable Collision Calculation
    physical_collision_detected = False
    collision_details: List[Dict[str, Any]] = []
    affected_requests: List[MaintenanceRequestORM] = []
    headway_buffer_min = 10

    if target_train:
        # Train-specific delay injection across its route occupancies
        for occ in target_train.occupancies:
            t0_delayed = occ.t0_min + delay_min
            t1_delayed = occ.t1_min + delay_min

            for req in approved_requests:
                if sections_match(occ.section_id, req.section_id):
                    blk_start = req.scheduled_start_min
                    blk_end = req.scheduled_end_min or (blk_start + req.duration_minutes)
                    
                    # Effective block interval with Indian Railways headway safety buffer
                    eff_start = blk_start - headway_buffer_min
                    eff_end = blk_end + headway_buffer_min

                    # Overlap check between delayed train and maintenance possession
                    if max(t0_delayed, eff_start) < min(t1_delayed, eff_end):
                        overlap_duration = min(t1_delayed, eff_end) - max(t0_delayed, eff_start)
                        physical_collision_detected = True
                        if req not in affected_requests:
                            affected_requests.append(req)
                        
                        target_section_id = req.section_id
                        collision_details.append({
                            "request_id": req.id,
                            "section_id": req.section_id,
                            "train_no": target_train.no,
                            "train_name": target_train.name,
                            "normal_slot": [occ.t0_min, occ.t1_min],
                            "delayed_slot": [t0_delayed, t1_delayed],
                            "block_slot": [blk_start, blk_end],
                            "headway_buffer_min": headway_buffer_min,
                            "overlap_min": overlap_duration,
                            "clash_type": "TIMETABLE_POSSESSION_CONFLICT",
                        })
    elif payload.incident_type == IncidentType.TRAIN_DELAY and payload.train_no:
        # Train not found in timetable: no physical train route occupancies to clash with
        physical_collision_detected = False
        collision_details.append({
            "train_no": payload.train_no,
            "status": "NOT_FOUND",
            "message": f"Train {payload.train_no} not found in Southern Railway Kerala corridor timetable. No schedule collision detected.",
        })
    else:
        # Non-train specific section incident (e.g. OHE breakdown, Track defect)
        for req in approved_requests:
            if sections_match(target_section_id, req.section_id):
                physical_collision_detected = True
                if req not in affected_requests:
                    affected_requests.append(req)
                collision_details.append({
                    "request_id": req.id,
                    "section_id": req.section_id,
                    "incident_type": payload.incident_type.value,
                    "duration_min": delay_min,
                    "clash_type": "CORRIDOR_SECTION_BLOCKAGE",
                })

    # 5. Query active blocks for LAYA context
    active_blocks = [
        {"request_id": r.id, "section_id": r.section_id, "start": r.scheduled_start_min, "end": r.scheduled_end_min}
        for r in approved_requests
    ]

    # 6. Run LAYA Advisory Incident Decision
    laya_adapter = get_laya_adapter()
    laya_context = {
        "active_count": len(active_blocks),
        "physical_collision_calculated": physical_collision_detected,
        "affected_count": len(affected_requests),
    }
    
    laya_decision = laya_adapter.evaluate_incident(payload, active_blocks, context=laya_context)
    
    # Authoritative physical collision override:
    # LAYA provides operational reasoning, but physical feasibility determines ground truth
    laya_decision.affects_active_block = physical_collision_detected
    laya_decision.triggers_reoptimization = physical_collision_detected
    laya_decision.affected_sections = list(set([r.section_id for r in affected_requests] or [target_section_id]))

    # 7. Record Incident in SQLite DB
    inc_orm = IncidentORM(
        id=f"INC-{uuid4().hex[:8]}",
        incident_type=payload.incident_type.value,
        section_id=target_section_id,
        train_no=payload.train_no,
        delay_min=delay_min,
        description=payload.description or f"{payload.incident_type.value} incident (+{delay_min}m)",
        severity=laya_decision.severity,
        affects_active_block=laya_decision.affects_active_block,
        triggers_reoptimization=laya_decision.triggers_reoptimization,
        affected_sections_json=json.dumps(laya_decision.affected_sections),
        laya_confidence=laya_decision.confidence,
        latency_ms=laya_decision.latency_ms,
        model_version=laya_decision.model_version,
    )
    db.add(inc_orm)
    db.commit()

    # 8. Audit: incident_evaluated
    await log_audit_event(
        db=db,
        event_type=AuditEventType.INCIDENT_EVALUATED.value,
        actor="LAYA Advisory Incident Model",
        input_payload=payload.model_dump(),
        output_payload=laya_decision.model_dump(),
        latency_ms=laya_decision.latency_ms,
        model_version=laya_decision.model_version,
        decision=f"Severity: {laya_decision.severity}, Collision: {physical_collision_detected}",
        metadata={"incident_id": inc_orm.id},
    )

    new_candidates: List[CandidateWindow] = []
    reoptimization_status = "NOT_REQUIRED"

    # 9. Reoptimization Execution (if collision detected)
    if physical_collision_detected and affected_requests:
        reoptimization_status = "COMPLETED"

        # Build dynamic timetable reflecting delayed trains
        delayed_timetable: List[TrainModel] = []
        for tr in TRAIN_TIMETABLE:
            if target_train and tr.no == target_train.no:
                shifted_occ = [
                    SectionOccupancy(
                        section_id=o.section_id,
                        t0_min=o.t0_min + delay_min,
                        t1_min=o.t1_min + delay_min,
                    )
                    for o in tr.occupancies
                ]
                delayed_timetable.append(
                    tr.model_copy(update={"occupancies": shifted_occ, "delay_min": delay_min})
                )
            else:
                delayed_timetable.append(tr)

        for req in affected_requests:
            # Transition status: mark approved block as REOPTIMIZATION_REQUIRED
            req.status = RequestStatus.REOPTIMIZATION_REQUIRED.value

            # Audit: active_block_affected
            await log_audit_event(
                db=db,
                event_type=AuditEventType.ACTIVE_BLOCK_AFFECTED.value,
                request_id=req.id,
                actor="Deterministic Timetable Collision Engine",
                decision="REOPTIMIZATION_REQUIRED",
                metadata={
                    "incident_id": inc_orm.id,
                    "train_no": payload.train_no,
                    "delay_min": delay_min,
                    "section_id": req.section_id,
                    "scheduled_start": req.scheduled_start_min,
                    "scheduled_end": req.scheduled_end_min,
                },
            )

            # Audit: reoptimization_triggered
            await log_audit_event(
                db=db,
                event_type=AuditEventType.REOPTIMIZATION_TRIGGERED.value,
                request_id=req.id,
                actor="RailSync Reoptimization Engine",
                decision="REOPTIMIZATION_REQUIRED",
                metadata={"incident_id": inc_orm.id, "reason": "Timetable possession collision detected"},
            )

            # Run physical constraint planner with delayed timetable
            cands = await execute_block_planning(
                db=db,
                request_orm=req,
                horizon_hours=24,
                max_candidates=3,
                actor="Disruption Reoptimizer",
                timetable=delayed_timetable,
            )
            # Maintain status as REOPTIMIZATION_REQUIRED until human controller approves replacement
            req.status = RequestStatus.REOPTIMIZATION_REQUIRED.value
            db.commit()

            # Evaluate each newly generated candidate with LAYA (Second Decision Point)
            for c in cands:
                laya_eval = await evaluate_candidate_window(
                    db=db,
                    candidate_id=c.candidate_id,
                    actor="LAYA Reoptimization Evaluator",
                )
                c.laya_evaluation = laya_eval
                new_candidates.append(c)

            # Audit: reoptimization_completed
            await log_audit_event(
                db=db,
                event_type=AuditEventType.REOPTIMIZATION_COMPLETED.value,
                request_id=req.id,
                actor="RailSync Reoptimization Engine",
                output_payload={
                    "candidate_count": len(cands),
                    "top_candidate": cands[0].candidate_id if cands else None,
                },
                decision="REOPTIMIZATION_COMPLETED",
                metadata={"incident_id": inc_orm.id},
            )

        db.commit()

    else:
        # Audit: reoptimization_not_required
        await log_audit_event(
            db=db,
            event_type=AuditEventType.REOPTIMIZATION_NOT_REQUIRED.value,
            actor="Deterministic Timetable Collision Engine",
            output_payload={"reason": "Delayed train passes with safe headway buffer; approved block remains valid"},
            decision="SCHEDULE_INTACT",
            metadata={"incident_id": inc_orm.id, "train_no": payload.train_no, "delay_min": delay_min},
        )

    # 10. AI-Driven Mitigation Strategies tailored to incident
    train_lbl = f"{target_train.no} ({target_train.name})" if target_train else (payload.train_no or "Delayed Service")
    top_new_slot = f"{new_candidates[0].start_time}–{new_candidates[0].end_time}" if new_candidates else "Next Feasible Window"

    mitigation_strategies = [
        {
            "option": "Option A — Loop Buffering",
            "title": "Loop Buffering & Preceding Regulation",
            "action": f"Park {train_lbl} at nearest loop line siding before {target_section_id} to clear path for approved maintenance.",
            "impact": "Preserves original approved engineering block without requiring track rescheduling.",
        },
        {
            "option": "Option B — Window Shift / Re-slotting",
            "title": "Dynamic Maintenance Window Shift",
            "action": f"Shift possession window to freshly generated slot ({top_new_slot}) calculated by physical constraint planner.",
            "impact": "Eliminates train delay; requires Section Controller verification and approval in Block Optimiser.",
        },
        {
            "option": "Option C — Priority Path Deviation",
            "title": "Single Line Working / Chord Diversion",
            "action": f"Implement temporary single-line working on opposite line under Indian Railways G&SR 15.06 pilot guard rules.",
            "impact": "Maintains both train flow and maintenance execution at regulated caution speed (25 km/h).",
        },
    ]

    total_latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

    result = DisruptionSimulationResult(
        incident_id=inc_orm.id,
        incident_type=payload.incident_type.value,
        train_no=payload.train_no,
        delay_min=delay_min,
        section_id=target_section_id,
        physical_collision_detected=physical_collision_detected,
        collision_details=collision_details,
        affects_active_block=laya_decision.affects_active_block,
        triggers_reoptimization=laya_decision.triggers_reoptimization,
        affected_blocks=[
            {
                "request_id": r.id,
                "section_id": r.section_id,
                "status": r.status,
                "scheduled_start": r.scheduled_start_min,
                "scheduled_end": r.scheduled_end_min,
            }
            for r in affected_requests
        ],
        reoptimization_status=reoptimization_status,
        new_candidates=new_candidates,
        laya_incident_decision=laya_decision,
        mitigation_strategies=mitigation_strategies,
        latency_ms=total_latency_ms,
    )

    # Broadcast live SSE update
    await broadcaster.broadcast("incident_simulated", result.model_dump())

    return result
