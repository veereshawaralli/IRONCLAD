"""Sustained local live-event fan-out benchmark, not a browser rendering benchmark."""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import httpx
import websockets

from ironclad.schema import Agent, Message
from ironclad.store import Store


async def benchmark(clients: int, seconds: int, port: int) -> dict[str, object]:
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{port}", trust_env=False
    ) as http:
        response = await http.post(
            "/api/login", json={"token": os.environ["IRONCLAD_ADMIN_TOKEN"]}
        )
        response.raise_for_status()
        cookie = "ironclad_session=" + http.cookies["ironclad_session"]
        response = await http.post(
            "/api/demo", headers={"X-Ironclad-Intent": "dashboard"}
        )
        response.raise_for_status()
        rid = response.json()["id"]
    stop_seq = 8 + seconds * 5
    ready = 0
    barrier = asyncio.Event()
    samples = []
    failures = []

    async def receive(index: int) -> None:
        nonlocal ready
        try:
            async with websockets.connect(
                f"ws://127.0.0.1:{port}/api/runs/{rid}/stream?after=8",
                additional_headers={"Cookie": cookie},
                proxy=None,
                open_timeout=60,
                max_queue=1024,
            ) as ws:
                first = json.loads(await ws.recv())
                assert first.get("heartbeat")
                ready += 1
                if ready == clients:
                    barrier.set()
                last = 8
                while last < stop_seq:
                    data = json.loads(await asyncio.wait_for(ws.recv(), seconds + 20))
                    if "seq" not in data:
                        continue
                    assert data["seq"] == last + 1
                    last = data["seq"]
                    samples.append(
                        (time.time_ns() - int(data["payload"]["sent_ns"])) / 1000000
                    )
        except Exception as exc:  # noqa: BLE001 -- record client failure without aborting other clients
            failures.append(type(exc).__name__)
            barrier.set()

    async def produce() -> None:
        await asyncio.wait_for(barrier.wait(), 60)
        if ready != clients:
            return

        def emit(seq: int) -> None:
            store = Store(Path(os.environ["IRONCLAD_DB"]))
            try:
                store.append(
                    Message(
                        run_id=rid,
                        seq=seq,
                        agent=Agent.WATCHER,
                        kind="incident",
                        payload={"simulated": True, "sent_ns": time.time_ns()},
                        timestamp="2026-11-10T00:00:00Z",
                        duration_ms=0,
                    )
                )
            finally:
                store.db.close()

        for seq in range(9, stop_seq + 1):
            await asyncio.to_thread(emit, seq)
            await asyncio.sleep(0.2)

    started = time.monotonic()
    await asyncio.gather(*(receive(i) for i in range(clients)), produce())
    samples.sort()
    return {
        "clients": clients,
        "duration_seconds": seconds,
        "events_per_client": seconds * 5,
        "received_events": len(samples),
        "failures": len(failures),
        "p50_delivery_ms": round(samples[int(len(samples) * 0.5)], 2)
        if samples
        else None,
        "p95_delivery_ms": round(samples[int(len(samples) * 0.95)], 2)
        if samples
        else None,
        "p99_delivery_ms": round(samples[int(len(samples) * 0.99)], 2)
        if samples
        else None,
        "wall_seconds": round(time.monotonic() - started, 2),
        "scope": "local persisted event to WebSocket receive; includes persistence/poll/fan-out, excludes browser rendering",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clients", type=int, default=500)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--port", type=int, default=8123)
    args = parser.parse_args()
    if not 1 <= args.clients <= 500 or not 1 <= args.seconds <= 60:
        parser.error("client/duration bounds exceeded")
    result = asyncio.run(benchmark(args.clients, args.seconds, args.port))
    print(json.dumps(result, indent=2))
    if result["failures"]:
        raise SystemExit(1)
