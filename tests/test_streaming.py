import asyncio

from ironclad.schema import Agent, Message
from ironclad.store import Store
from ironclad.streaming import EventHub


def test_shared_hub_replay_and_live_event(tmp_path):
    path = tmp_path / "stream.db"
    store = Store(path)
    store.begin("run", {"log": "fixture"})

    def event(seq):
        return Message(
            run_id="run",
            seq=seq,
            agent=Agent.WATCHER,
            kind="incident",
            payload={},
            timestamp="2026-11-10T00:00:00Z",
            duration_ms=0,
        )

    store.append(event(1))

    async def check():
        hub = EventHub(path)
        await hub.start()
        try:
            q1, replay = await hub.subscribe("run", 1)
            q2, _ = await hub.subscribe("run", 1)
            assert not replay
            await asyncio.to_thread(lambda: Store(path).append(event(2)))

            async def next_live(queue):
                while True:
                    value = await asyncio.wait_for(queue.get(), 1)
                    if value.seq == 2:
                        return value

            a, b = await asyncio.gather(next_live(q1), next_live(q2))
            assert a.seq == b.seq == 2
            assert len(hub.topics) == 1
            hub.unsubscribe("run", q1)
            hub.unsubscribe("run", q2)
        finally:
            await hub.stop()

    asyncio.run(check())
