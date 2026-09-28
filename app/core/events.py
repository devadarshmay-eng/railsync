import asyncio
import json
from typing import AsyncGenerator, Dict, List, Set


class EventBroker:
    """In-memory publish/subscribe event bus for real-time SSE streaming to frontend clients."""

    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()

    async def subscribe(self) -> AsyncGenerator[str, None]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                data = await queue.get()
                yield data
        finally:
            self._subscribers.remove(queue)

    async def publish(self, event_type: str, data: Dict) -> None:
        message = json.dumps({"event": event_type, "data": data})
        formatted = f"event: {event_type}\ndata: {message}\n\n"
        
        # Broadcast non-blocking to all connected frontend clients
        for q in list(self._subscribers):
            try:
                q.put_nowait(formatted)
            except asyncio.QueueFull:
                pass

    async def broadcast(self, event_type: str, data: Dict) -> None:
        await self.publish(event_type, data)


event_broker = EventBroker()
broadcaster = event_broker
