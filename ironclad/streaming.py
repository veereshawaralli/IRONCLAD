"""One poll per active run, shared by all subscribers; sequence replay stays durable."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from .schema import Message
from .store import Store


@dataclass
class Topic:
    cursor: int = 0
    subscribers: set[asyncio.Queue[Message | None]] = field(default_factory=set)


class EventHub:
    def __init__(self, path: Path):
        self.path = path
        self.topics: dict[str, Topic] = {}
        self.task: asyncio.Task[None] | None = None

    def read(self, rid: str, after: int) -> list[Message]:
        store = Store(self.path)
        try:
            store.input(rid)
            return store.events(rid, after)
        finally:
            store.db.close()

    async def start(self) -> None:
        self.task = asyncio.create_task(self.poll())

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def poll(self) -> None:
        while True:
            for rid, topic in list(self.topics.items()):
                if not topic.subscribers:
                    self.topics.pop(rid, None)
                    continue
                batch = await asyncio.to_thread(self.read, rid, topic.cursor)
                for event in batch:
                    topic.cursor = event.seq
                    for queue in list(topic.subscribers):
                        try:
                            queue.put_nowait(event)
                        except asyncio.QueueFull:
                            # Never silently discard a step. Force durable replay.
                            while not queue.empty():
                                queue.get_nowait()
                            queue.put_nowait(None)
                            topic.subscribers.discard(queue)
            await asyncio.sleep(0.03)

    async def subscribe(
        self, rid: str, after: int
    ) -> tuple[asyncio.Queue[Message | None], list[Message]]:
        queue: asyncio.Queue[Message | None] = asyncio.Queue(maxsize=256)
        topic = self.topics.setdefault(rid, Topic())
        topic.subscribers.add(queue)
        try:
            replay = await asyncio.to_thread(self.read, rid, after)
            return queue, replay
        except BaseException:
            topic.subscribers.discard(queue)
            raise

    def unsubscribe(self, rid: str, queue: asyncio.Queue[Message | None]) -> None:
        topic = self.topics.get(rid)
        if topic:
            topic.subscribers.discard(queue)
