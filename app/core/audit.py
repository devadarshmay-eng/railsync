import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4
from sqlalchemy.orm import Session
from app.core.events import event_broker
from app.db.models import AuditEventORM


async def log_audit_event(
    db: Session,
    event_type: str,
    actor: str = "system",
    request_id: Optional[str] = None,
    input_payload: Optional[Dict[str, Any]] = None,
    output_payload: Optional[Dict[str, Any]] = None,
    latency_ms: Optional[float] = None,
    model_version: Optional[str] = None,
    decision: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditEventORM:
    """Store an immutable audit trail entry and broadcast it over SSE."""
    now = datetime.now(timezone.utc)
    event_id = f"EVT-{now.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
    
    event = AuditEventORM(
        id=event_id,
        event_type=event_type,
        request_id=request_id,
        actor=actor,
        input_payload=json.dumps(input_payload or {}),
        output_payload=json.dumps(output_payload or {}),
        latency_ms=latency_ms,
        model_version=model_version,
        decision=decision,
        metadata_json=json.dumps(metadata or {}),
        timestamp=now,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    # Publish over live event stream
    await event_broker.publish(
        event_type=event_type,
        data={
            "event_id": event_id,
            "request_id": request_id,
            "actor": actor,
            "latency_ms": latency_ms,
            "decision": decision,
            "timestamp": event.timestamp.isoformat(),
        }
    )

    return event
