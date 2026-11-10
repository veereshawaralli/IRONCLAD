import asyncio
import hashlib
import hmac
import os
import secrets
import shutil
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .fleet import Fleet
from .knowledge import retrieve
from .redaction import redact
from .schema import Agent, FleetPolicy
from .sessions import Sessions
from .store import Store
from .streaming import EventHub


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    log: str = Field(min_length=1, max_length=24000)
    mode: str = "demo"


class Login(BaseModel):
    token: str = Field(max_length=512)


def create_app() -> FastAPI:
    db = Path(os.environ.get("IRONCLAD_DB", ".ironclad/events.db"))
    hub = EventHub(db)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        await hub.start()
        try:
            yield
        finally:
            await hub.stop()

    app = FastAPI(title="IRONCLAD", version="1.0.0", lifespan=lifespan)
    repo = Path(os.environ.get("IRONCLAD_REPO", "examples/broken_repo")).resolve()
    secret = os.environ.get("IRONCLAD_ADMIN_TOKEN", "")
    if len(secret) < 24:
        raise RuntimeError("Set IRONCLAD_ADMIN_TOKEN to at least 24 random characters")
    sessions = Sessions(db, secret)

    def store() -> Store:
        return Store(db)

    def authenticate(request: Request) -> None:
        if not sessions.valid(request.cookies.get("ironclad_session", "")):
            raise HTTPException(401, "Sign in required")
        if (
            request.method not in {"GET", "HEAD"}
            and request.headers.get("X-Ironclad-Intent") != "dashboard"
        ):
            raise HTTPException(403, "Missing request intent")

    from .http_limits import BodyLimit

    app.add_middleware(BodyLimit, max_bytes=1000000)

    failures: dict[str, list[float]] = {}

    @app.post("/api/login")
    def login(body: Login, response: Response, request: Request) -> dict[str, bool]:
        address = request.client.host if request.client else "unknown"
        now = time.monotonic()
        attempts = [t for t in failures.get(address, []) if now - t < 60]
        if len(attempts) >= 10:
            raise HTTPException(429, "Too many sign-in attempts; retry in one minute")
        if len(failures) > 10000:
            failures.clear()
        if not secrets.compare_digest(body.token, secret):
            failures[address] = attempts + [now]
            raise HTTPException(401, "Invalid access token")
        failures.pop(address, None)
        response.set_cookie(
            "ironclad_session",
            sessions.issue(),
            httponly=True,
            samesite="strict",
            secure=os.environ.get("IRONCLAD_SECURE_COOKIE") == "1",
            max_age=28800,
        )
        return {"ok": True}

    @app.post("/api/logout", dependencies=[Depends(authenticate)])
    def logout(response: Response, request: Request) -> dict[str, bool]:
        sessions.revoke(request.cookies.get("ironclad_session", ""))
        response.delete_cookie("ironclad_session")
        return {"ok": True}

    @app.get("/api/health", dependencies=[Depends(authenticate)])
    def health() -> dict[str, object]:
        return {
            "service": "operational",
            "docker": bool(shutil.which("docker")),
            "repository": repo.name,
            "model_configured": bool(os.environ.get("IRONCLAD_API_KEY")),
            "version": "0.3.0",
        }

    @app.get("/api/runs", dependencies=[Depends(authenticate)])
    def runs(
        limit: int = Query(200, ge=1, le=200), offset: int = Query(0, ge=0, le=1000000)
    ) -> list[dict[str, object]]:
        with_store = store()
        try:
            return with_store.list_runs(limit, offset)
        finally:
            with_store.db.close()

    @app.post("/api/runs", dependencies=[Depends(authenticate)])
    def submit(body: RunRequest) -> dict[str, str]:
        if body.mode not in {"demo", "hosted"}:
            raise HTTPException(422, "Unsupported mode")
        s = store()
        try:
            rid = uuid4().hex
            policy = FleetPolicy.model_validate(s.settings() or {})
            s.begin(
                rid,
                {
                    "repo": str(repo),
                    "log": redact(body.log),
                    "mode": body.mode,
                    "policy": policy.model_dump(),
                },
            )
            s.queue(rid)
            return {"id": rid}
        finally:
            s.db.close()

    @app.get("/api/runs/{rid}", dependencies=[Depends(authenticate)])
    def detail(rid: str) -> dict[str, object]:
        s = store()
        try:
            data = s.input(rid)
            return {
                "id": rid,
                "mode": data.get("mode"),
                "events": [e.model_dump() for e in s.events(rid)],
            }
        except ValueError:
            raise HTTPException(404, "Unknown run") from None
        finally:
            s.db.close()

    @app.websocket("/api/runs/{rid}/stream")
    async def stream(ws: WebSocket, rid: str, after: int = 0) -> None:
        if not await asyncio.to_thread(
            sessions.valid, ws.cookies.get("ironclad_session", "")
        ):
            await ws.close(code=4401)
            return
        origin = ws.headers.get("origin")
        if origin and origin.split("://", 1)[-1] != ws.headers.get("host"):
            await ws.close(code=4403)
            return
        try:
            queue, replay = await hub.subscribe(rid, max(after, 0))
        except ValueError:
            await ws.close(code=4404)
            return
        await ws.accept()
        cursor = max(after, 0)

        async def disconnected() -> None:
            while True:
                if (await ws.receive())["type"] == "websocket.disconnect":
                    return

        closed = asyncio.create_task(disconnected())
        try:
            for event in replay:
                await ws.send_json(event.model_dump())
                cursor = event.seq
            await ws.send_json({"heartbeat": True, "cursor": cursor})
            while True:
                try:
                    waiting = asyncio.create_task(queue.get())
                    try:
                        done, _ = await asyncio.wait(
                            {waiting, closed},
                            timeout=15,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if closed in done:
                            return
                        if waiting not in done:
                            raise TimeoutError
                        incoming = waiting.result()
                    finally:
                        if not waiting.done():
                            waiting.cancel()
                except TimeoutError:
                    if not await asyncio.to_thread(
                        sessions.valid, ws.cookies.get("ironclad_session", "")
                    ):
                        await ws.close(code=4401)
                        return
                    await ws.send_json({"heartbeat": True, "cursor": cursor})
                    continue
                if incoming is None:
                    await ws.close(
                        code=1013,
                        reason="Slow client: reconnect with last event sequence",
                    )
                    return
                if incoming.seq > cursor:
                    await ws.send_json(incoming.model_dump())
                    cursor = incoming.seq
        except (WebSocketDisconnect, RuntimeError):
            return
        finally:
            closed.cancel()
            hub.unsubscribe(rid, queue)

    @app.get("/api/knowledge", dependencies=[Depends(authenticate)])
    def knowledge(q: str = "average") -> dict[str, object]:
        if len(q) > 1000:
            raise HTTPException(422, "Query too long")
        try:
            s = store()
            try:
                citations = retrieve(repo, q, 24000, s)
            finally:
                s.db.close()
            return {
                "strategy": "AST + BM25 / optional pgvector RRF",
                "repository": repo.name,
                "results": [e.model_dump() for e in citations],
            }
        except ValueError as exc:
            return {
                "strategy": "AST + BM25 / optional pgvector RRF",
                "results": [],
                "message": str(exc),
            }

    @app.get("/api/settings", dependencies=[Depends(authenticate)])
    def settings() -> dict[str, object]:
        s = store()
        try:
            return FleetPolicy.model_validate(s.settings()).model_dump()
        finally:
            s.db.close()

    @app.put("/api/settings", dependencies=[Depends(authenticate)])
    def update_settings(policy: FleetPolicy) -> dict[str, object]:
        s = store()
        try:
            s.save_settings(policy.model_dump())
            return policy.model_dump()
        finally:
            s.db.close()

    @app.post("/api/demo", dependencies=[Depends(authenticate)])
    def demo() -> dict[str, str]:
        # Recorded synthetic events are explicitly marked; cannot be published as a PR.
        s = store()
        rid = uuid4().hex
        s.begin(
            rid,
            {
                "mode": "simulation",
                "log": "ZeroDivisionError: empty collection",
                "repo": str(repo),
            },
        )
        fleet = Fleet(s, None)
        rows = [
            (
                Agent.WATCHER,
                "incident",
                {"summary": "ZeroDivisionError: empty collection", "severity": "high"},
            ),
            (
                Agent.DIAGNOSTICIAN,
                "diagnosis",
                {
                    "hypothesis": "The average function divides by the length of an empty collection.",
                    "confidence": 0.98,
                    "evidence": [
                        {
                            "path": "stats.py",
                            "start_line": 1,
                            "end_line": 3,
                            "text": "return sum(values) / len(values)",
                        }
                    ],
                },
            ),
            (
                Agent.SURGEON,
                "proposal",
                {
                    "summary": "Handle empty input",
                    "diff": "--- a/stats.py\n+++ b/stats.py\n@@ -1,3 +1,5 @@\n def average(values):\n+    if not values:\n+        return 0.0\n     return sum(values) / len(values)\n",
                    "attempt": 1,
                },
            ),
            (
                Agent.VERIFIER,
                "verification",
                {
                    "passed": False,
                    "checks": {"tests": False},
                    "output": "Simulated failure: test_empty",
                    "attempt": 1,
                },
            ),
            (
                Agent.DIAGNOSTICIAN,
                "diagnosis",
                {
                    "hypothesis": "Reflect on the failed assertion and enforce the documented zero-result contract.",
                    "confidence": 0.99,
                    "evidence": [],
                    "attempt": 2,
                },
            ),
            (
                Agent.SURGEON,
                "proposal",
                {
                    "summary": "Preserve empty-input contract",
                    "diff": "--- a/stats.py\n+++ b/stats.py\n@@ -1,3 +1,5 @@\n def average(values):\n+    if not values:\n+        return 0.0\n     return sum(values) / len(values)\n",
                    "attempt": 2,
                },
            ),
            (
                Agent.VERIFIER,
                "verification",
                {
                    "passed": True,
                    "checks": {
                        "tests": True,
                        "lint": True,
                        "types": True,
                        "security": True,
                    },
                    "output": "Simulated checks passed; no code executed",
                    "attempt": 2,
                },
            ),
            (
                Agent.REPORTER,
                "report",
                {
                    "title": "fix: handle empty input in average",
                    "body": "Synthetic replay for dashboard exploration. No actual verification or PR.",
                    "status": "simulation",
                },
            ),
        ]
        for i, (agent, kind, payload) in enumerate(rows):
            fleet.emit(
                rid,
                agent,
                kind,
                {**cast(dict[str, object], payload), "simulated": True},
                time.monotonic() - (i + 1) * 0.12,
            )
        s.db.close()
        return {"id": rid}

    @app.post("/api/runs/{rid}/approve", dependencies=[Depends(authenticate)])
    def approve(rid: str, body: dict[str, bool]) -> dict[str, bool]:
        from .review import Review

        s = store()
        try:
            Review(s).approve(rid, body.get("confirmed", False))
            return {"approved": True}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        finally:
            s.db.close()

    @app.post("/api/runs/{rid}/publish", dependencies=[Depends(authenticate)])
    def publish(rid: str) -> dict[str, str]:
        from .github import GitHub
        from .review import Review

        s = store()
        try:
            return {"url": Review(s).publish(rid, GitHub())}
        except (ValueError, KeyError) as exc:
            raise HTTPException(
                409,
                str(exc)
                if type(exc) is ValueError
                else "Configure GitHub repository and token on the server",
            ) from None
        finally:
            s.db.close()

    @app.post("/api/webhooks/github")
    async def webhook(request: Request) -> dict[str, object]:
        import json

        signing = os.environ.get("IRONCLAD_WEBHOOK_SECRET", "")
        if len(signing) < 24:
            raise HTTPException(503, "Webhook signing secret not configured")
        raw = await request.body()
        if len(raw) > 1000000:
            raise HTTPException(413, "Webhook payload too large")
        expected = (
            "sha256=" + hmac.new(signing.encode(), raw, hashlib.sha256).hexdigest()
        )
        if not hmac.compare_digest(
            request.headers.get("X-Hub-Signature-256", ""), expected
        ):
            raise HTTPException(401, "Invalid webhook signature")
        payload = json.loads(raw)
        if payload.get("repository", {}).get("full_name") != os.environ.get(
            "IRONCLAD_GITHUB_REPO"
        ):
            raise HTTPException(403, "Webhook repository outside configured scope")
        if (
            request.headers.get("X-GitHub-Event") != "check_run"
            or payload.get("action") != "completed"
            or payload.get("check_run", {}).get("conclusion")
            not in {"failure", "timed_out"}
        ):
            return {"ignored": True}
        delivery = request.headers.get("X-GitHub-Delivery", "")
        if not delivery or len(delivery) > 128:
            raise HTTPException(422, "Delivery identifier required")
        s = store()
        try:
            s.db.execute(
                "CREATE TABLE IF NOT EXISTS deliveries(id TEXT PRIMARY KEY,run_id TEXT)"
            )
            previous = s.db.execute(
                "SELECT run_id FROM deliveries WHERE id=?", (delivery,)
            ).fetchone()
            if previous:
                return {"id": previous[0], "duplicate": True}
            check = payload["check_run"]
            output = check.get("output") or {}
            log = (
                str(output.get("title", "CI failure"))
                + "\n"
                + str(output.get("summary", ""))
            )[:24000]
            rid = uuid4().hex
            s.begin(
                rid,
                {
                    "repo": str(repo),
                    "log": redact(log),
                    "mode": "hosted",
                    "policy": FleetPolicy.model_validate(s.settings()).model_dump(),
                    "head_sha": check.get("head_sha"),
                },
            )
            with s.db:
                s.db.execute("INSERT INTO deliveries VALUES(?,?)", (delivery, rid))
                s.db.execute("INSERT INTO jobs(id,status) VALUES(?,'queued')", (rid,))
            return {"id": rid}
        finally:
            s.db.close()

    @app.get("/api/metrics", dependencies=[Depends(authenticate)])
    def metrics() -> Response:
        s = store()
        try:
            runs = s.list_runs()
            events = [e for r in runs for e in s.events(str(r["id"]))]
            durations = sorted(e.duration_ms for e in events)
            p95 = (
                durations[min(len(durations) - 1, int(len(durations) * 0.95))]
                if durations
                else 0
            )
            reserved = sum(float(str(r["reserved_usd"])) for r in runs)
            text = (
                "\n".join(
                    [
                        "# TYPE ironclad_incidents gauge",
                        f"ironclad_incidents {len(runs)}",
                        f"ironclad_steps {len(events)}",
                        f"ironclad_agent_duration_p95_ms {p95}",
                        f"ironclad_reserved_usd {reserved}",
                        f"ironclad_escalations {sum(r['status'] == 'escalated' for r in runs)}",
                        f"ironclad_draft_prs {sum(e.kind == 'pull_request' for e in events)}",
                    ]
                )
                + "\n"
            )
            return Response(text, media_type="text/plain; version=0.0.4")
        finally:
            s.db.close()

    output = Path(__file__).resolve().parents[1] / "web" / "out"
    if output.exists():
        app.mount("/", StaticFiles(directory=output, html=True), name="dashboard")
    return app
