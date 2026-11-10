"""Optional Redis Streams relay. SQLite event history remains authoritative."""

from typing import Any

from .schema import Message


class RedisBus:
    def __init__(self, client: Any):
        self.client = client

    def publish(self, event: Message) -> str:
        # One stream per run, deterministic IDs: retries cannot create duplicates.
        stream = "ironclad:run:" + event.run_id
        event_id = f"{event.seq}-0"
        existing = self.client.xrange(stream, min=event_id, max=event_id)
        if not existing:
            try:
                self.client.xadd(
                    stream, {"message": event.model_dump_json()}, id=event_id
                )
            except Exception:
                if not self.client.xrange(stream, min=event_id, max=event_id):
                    raise
        return event_id
