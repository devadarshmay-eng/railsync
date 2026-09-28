from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from app.core.events import event_broker

router = APIRouter(prefix="/api/events", tags=["Live Real-Time Stream"])


@router.get("")
async def stream_live_events():
    """Server-Sent Events (SSE) stream broadcasting real-time block planning, LAYA decisions, and reoptimization events."""
    return EventSourceResponse(event_broker.subscribe())
