from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.adapters.laya import get_laya_adapter
from app.adapters.planner import get_block_planner
from app.core.safety import get_safety_headers
from app.db.database import get_db
from app.db.models import AuditEventORM, MaintenanceRequestORM
from app.db.seed import DATA_DISCLAIMER, MAINTENANCE_PRESETS, SECTIONS, STATIONS, TRAIN_TIMETABLE

router = APIRouter(prefix="/api", tags=["Health & System Metrics"])


@router.get("/health")
def health_check(response: Response):
    """System health check and adapter readiness status."""
    response.headers.update(get_safety_headers())
    laya_adapter = get_laya_adapter()
    planner = get_block_planner()

    return {
        "status": "healthy",
        "service": "RailSync AI",
        "advisory_mode": True,
        "laya": laya_adapter.get_model_metadata(),
        "planner": planner.get_solver_name(),
        "database": "SQLite (WAL Mode) / Operational",
    }


@router.get("/metrics")
def get_system_metrics(response: Response, db: Session = Depends(get_db)):
    """Real telemetry metrics including measured latencies and queue volume."""
    response.headers.update(get_safety_headers())
    total_requests = db.query(MaintenanceRequestORM).count()
    pending_review = db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.status == "AWAITING_REVIEW").count()
    approved = db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.status == "APPROVED").count()
    rejected = db.query(MaintenanceRequestORM).filter(MaintenanceRequestORM.status == "REJECTED").count()

    # Calculate real average latencies from audit log
    avg_laya_latency = db.query(func.avg(AuditEventORM.latency_ms)).filter(
        AuditEventORM.event_type.in_(["laya_triage_completed", "laya_candidate_evaluated"])
    ).scalar() or 0.0

    avg_planner_latency = db.query(func.avg(AuditEventORM.latency_ms)).filter(
        AuditEventORM.event_type == "planner_completed"
    ).scalar() or 0.0

    return {
        "status": "success",
        "metrics": {
            "total_requests": total_requests,
            "awaiting_review": pending_review,
            "approved": approved,
            "rejected": rejected,
            "measured_laya_avg_latency_ms": round(float(avg_laya_latency), 2),
            "measured_planner_avg_latency_ms": round(float(avg_planner_latency), 2),
        }
    }


@router.get("/demo/data")
def get_demo_reference_data(response: Response):
    """Returns Southern Railway Kerala Section demo stations, sections, trains, and presets."""
    response.headers.update(get_safety_headers())
    return {
        "disclaimer": DATA_DISCLAIMER,
        "stations": [s.model_dump() for s in STATIONS.values()],
        "sections": [s.model_dump() for s in SECTIONS.values()],
        "maintenance_presets": MAINTENANCE_PRESETS,
        "trains_count": len(TRAIN_TIMETABLE),
        "trains": [
            {
                "no": t.no,
                "name": t.name,
                "type": t.type,
                "route": t.route,
                "dep_min": t.dep_min,
                "speed_kmh": t.speed_kmh,
                "stops": len(t.schedule),
            }
            for t in TRAIN_TIMETABLE
        ]
    }
