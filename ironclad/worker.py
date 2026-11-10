"""Leased, fenced workers; Redis Streams wakeups with durable SQL recovery."""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from .fleet import Fleet
from .sandbox import DockerSandbox
from .schema import FleetPolicy
from .store import LeaseLost, Store


class Dispatcher:
    def __init__(self, owner: str):
        self.owner = owner
        self.client: Any = None
        url = os.environ.get("IRONCLAD_REDIS_URL")
        if url:
            import redis

            try:
                self.client = redis.Redis.from_url(
                    url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                try:
                    self.client.xgroup_create(
                        "ironclad:jobs", "workers", id="0", mkstream=True
                    )
                except redis.ResponseError as exc:
                    if "BUSYGROUP" not in str(exc):
                        raise
            except redis.RedisError:
                self.client = None

    def wait(self) -> list[str]:
        if self.client is None:
            time.sleep(0.25)
            return []
        import redis

        try:
            pending = self.client.xautoclaim(
                "ironclad:jobs",
                "workers",
                self.owner,
                min_idle_time=60000,
                start_id="0-0",
                count=10,
            )
            entries = pending[1]
            if not entries:
                messages = self.client.xreadgroup(
                    "workers", self.owner, {"ironclad:jobs": ">"}, count=10, block=250
                )
                entries = messages[0][1] if messages else []
            return [str(mid) for mid, _ in entries]
        except redis.RedisError:
            time.sleep(0.25)
            return []

    def acknowledge(self, ids: list[str]) -> None:
        if self.client and ids:
            import redis

            try:
                self.client.xack("ironclad:jobs", "workers", *ids)
            except redis.RedisError:
                pass


def process_one(path: Path, owner: str) -> bool:
    store = Store(path)
    rid = store.claim(owner)
    if not rid:
        store.db.close()
        return False
    stopped = threading.Event()

    def pulse() -> None:
        heartbeat = Store(path)
        try:
            while not stopped.wait(10):
                if not heartbeat.heartbeat(rid, owner):
                    return
        finally:
            heartbeat.db.close()

    thread = threading.Thread(target=pulse, daemon=True)
    thread.start()
    try:
        policy = FleetPolicy.model_validate(store.input(rid).get("policy", {}))
        Fleet(store, DockerSandbox(policy.timeout_seconds)).execute(rid)
        store.finish(rid)
    except LeaseLost:
        logging.getLogger("ironclad.worker").warning(
            "Stale worker stopped without modifying the new owner state"
        )
    finally:
        stopped.set()
        thread.join(timeout=2)
        store.db.close()
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    path = Path(os.environ.get("IRONCLAD_DB", ".ironclad/events.db"))
    owner = uuid4().hex
    dispatcher = Dispatcher(owner)
    while True:
        ids = dispatcher.wait()
        while process_one(path, owner):
            pass
        dispatcher.acknowledge(ids)


if __name__ == "__main__":
    main()
