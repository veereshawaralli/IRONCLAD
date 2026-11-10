import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from ironclad.schema import Agent, Message
from ironclad.store import LeaseLost, Store


def test_workers_claim_once(tmp_path):
    path = tmp_path / "queue.db"
    s = Store(path)
    s.begin("one", {"log": "fixture"})
    s.queue("one")

    def claim(owner):
        other = Store(path)
        try:
            return other.claim(owner)
        finally:
            other.db.close()

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(claim, ["a", "b"]))
    assert results.count("one") == 1
    assert results.count(None) == 1


def test_expired_worker_cannot_append_or_spend(tmp_path):
    path = tmp_path / "queue.db"
    first = Store(path)
    first.begin("one", {"log": "fixture"})
    first.queue("one")
    assert first.claim("a", lease_seconds=0.01) == "one"
    time.sleep(0.02)
    second = Store(path)
    assert second.claim("b") == "one"
    event = Message(
        run_id="one",
        seq=1,
        agent=Agent.WATCHER,
        kind="incident",
        payload={},
        timestamp="2026-11-10T00:00:00Z",
        duration_ms=0,
    )
    with pytest.raises(LeaseLost):
        first.append(event)
    with pytest.raises(LeaseLost):
        first.reserve("one", 0.1, 1, 10)
    assert second.heartbeat("one", "b")
    second.append(event)
    second.finish("one")
    assert second.claim("c") is None


def test_atomic_event_sequence_and_unique_approval(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "record.db"
    Store(path).begin("run", {"log": "fixture"})

    def append(index):
        s = Store(path)
        try:
            event = Message(
                run_id="run",
                seq=1,
                agent=Agent.SUPERVISOR,
                kind="approved",
                payload={"reviewed": True},
                timestamp="2026-11-10T00:00:00Z",
                duration_ms=0,
            )
            return s.record(event, unique_kind=True).seq
        finally:
            s.db.close()

    with ThreadPoolExecutor(4) as pool:
        assert list(pool.map(append, range(4))) == [1] * 4
    assert len(Store(path).events("run")) == 1


def test_health_reports_online_workers(tmp_path):
    store = Store(tmp_path / "health.db")
    assert store.fleet_health() == {"workers": 0, "docker": False, "queued": 0}
    store.worker_heartbeat("worker", True)
    assert store.fleet_health()["workers"] == 1
    assert store.fleet_health()["docker"]


def test_concurrent_webhooks_create_one_run(tmp_path):
    path = tmp_path / "deliveries.db"
    Store(path).db.close()

    def ingest(index):
        store = Store(path)
        try:
            return store.ingest_delivery("delivery", {"log": "fixture"})
        finally:
            store.db.close()

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(ingest, range(4)))
    assert len({rid for rid, duplicate in results}) == 1
    assert sum(not duplicate for rid, duplicate in results) == 1
    assert len(Store(path).list_runs()) == 1
