"""Service-backed integration suite; CI supplies ephemeral Postgres and Redis."""

import os
from pathlib import Path
from uuid import uuid4

import pytest

from ironclad.schema import Agent, Message
from ironclad.store import Store


@pytest.mark.skipif(
    not os.environ.get("IRONCLAD_TEST_POSTGRES"),
    reason="Ephemeral PostgreSQL not configured",
)
def test_postgres_durability_and_vector_index(tmp_path, monkeypatch):
    import psycopg

    from ironclad.knowledge import VectorIndex

    monkeypatch.setenv("IRONCLAD_DATABASE_URL", os.environ["IRONCLAD_TEST_POSTGRES"])
    monkeypatch.setenv("IRONCLAD_EMBEDDING_DIMENSIONS", "3")
    rid = uuid4().hex
    s = Store(tmp_path / "ignored.db")
    s.begin(rid, {"log": "fixture"})
    s.append(
        Message(
            run_id=rid,
            seq=1,
            agent=Agent.WATCHER,
            kind="incident",
            payload={"fixture": True},
            timestamp="2026-11-10T00:00:00Z",
            duration_ms=1,
        )
    )
    assert Store(tmp_path / "ignored.db").events(rid)[0].seq == 1
    s.reserve(rid, 0.2, 0.5, 3)
    with pytest.raises(ValueError):
        s.reserve(rid, 0.4, 0.5, 3)
    with pytest.raises(psycopg.Error):
        s.db.execute("DELETE FROM events WHERE run_id=?", (rid,))
    index = VectorIndex()
    monkeypatch.setattr("ironclad.knowledge.embed", lambda *args: [1.0, 0.0, 0.0])
    count = index.index(Path("examples/broken_repo"), s)
    assert count >= 1
    assert index.search(Path("examples/broken_repo"), [1, 0, 0])
    index.db.close()
    s.db.close()


@pytest.mark.skipif(
    not os.environ.get("IRONCLAD_TEST_REDIS"), reason="Ephemeral Redis not configured"
)
def test_live_redis_stream_relay():
    import redis

    from ironclad.bus import RedisBus

    client = redis.Redis.from_url(os.environ["IRONCLAD_TEST_REDIS"])
    rid = uuid4().hex
    event = Message(
        run_id=rid,
        seq=1,
        agent=Agent.WATCHER,
        kind="incident",
        payload={},
        timestamp="2026-11-10T00:00:00Z",
        duration_ms=0,
    )
    bus = RedisBus(client)
    bus.publish(event)
    bus.publish(event)
    assert client.xlen("ironclad:run:" + rid) == 1
    client.delete("ironclad:run:" + rid)
    client.close()


@pytest.mark.skipif(
    not os.environ.get("IRONCLAD_TEST_POSTGRES"),
    reason="Ephemeral PostgreSQL not configured",
)
def test_postgres_claim_and_fencing(tmp_path, monkeypatch):
    import time

    from ironclad.store import LeaseLost

    monkeypatch.setenv("IRONCLAD_DATABASE_URL", os.environ["IRONCLAD_TEST_POSTGRES"])
    rid = uuid4().hex
    first = Store(tmp_path / "unused.db")
    first.begin(rid, {"log": "lease fixture"})
    first.queue(rid)
    assert first.claim("worker-a") == rid
    second = Store(tmp_path / "unused.db")
    assert second.claim("worker-b") is None
    with second.db:
        second.db.execute(
            "UPDATE jobs SET lease_until=? WHERE id=?", (time.time() - 1, rid)
        )
    assert second.claim("worker-b") == rid
    with pytest.raises(LeaseLost):
        first.reserve(rid, 0.1, 1, 10)
    assert second.heartbeat(rid, "worker-b")
    second.finish(rid)
    first.db.close()
    second.db.close()
