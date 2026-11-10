import asyncio
import hashlib
import hmac
import os
import secrets
import shutil
import time
from pathlib import Path
from typing import cast
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .fleet import Fleet
from .repository import retrieve
from .schema import Agent, FleetPolicy
from .store import Store


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    log: str = Field(min_length=1, max_length=24000)
    mode: str = "demo"


class Login(BaseModel):
    token: str = Field(max_length=512)


def create_app() -> FastAPI:
    app = FastAPI(title="IRONCLAD", version="0.3.0")
    db = Path(os.environ.get("IRONCLAD_DB", ".ironclad/events.db"))
    repo = Path(os.environ.get("IRONCLAD_REPO", "examples/broken_repo")).resolve()
    secret = os.environ.get("IRONCLAD_ADMIN_TOKEN", "")
    if len(secret) < 24:
        raise RuntimeError("Set IRONCLAD_ADMIN_TOKEN to at least 24 random characters")
    cookie = hmac.new(
        secret.encode(), b"ironclad-session-v1", hashlib.sha256
    ).hexdigest()

    def store() -> Store:
        return Store(db)

    def authenticate(request: Request) -> None:
        if not secrets.compare_digest(
            request.cookies.get("ironclad_session", ""), cookie
        ):
            raise HTTPException(401, "Sign in required")
        if (
            request.method not in {"GET", "HEAD"}
            and request.headers.get("X-Ironclad-Intent") != "dashboard"
        ):
            raise HTTPException(403, "Missing request intent")

    @app.post("/api/login")
    def login(body: Login, response: Response) -> dict[str, bool]:
        if not secrets.compare_digest(body.token, secret):
            raise HTTPException(401, "Invalid access token")
        response.set_cookie(
            "ironclad_session",
            cookie,
            httponly=True,
            samesite="strict",
            secure=os.environ.get("IRONCLAD_SECURE_COOKIE") == "1",
            max_age=28800,
        )
        return {"ok": True}

    @app.post("/api/logout", dependencies=[Depends(authenticate)])
    def logout(response: Response) -> dict[str, bool]:
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
    def runs() -> list[dict[str, object]]:
        with_store = store()
        try:
            return with_store.list_runs()
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
                    "log": body.log,
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
        if not secrets.compare_digest(ws.cookies.get("ironclad_session", ""), cookie):
            await ws.close(code=4401)
            return
        origin = ws.headers.get("origin")
        if origin and origin.split("://", 1)[-1] != ws.headers.get("host"):
            await ws.close(code=4403)
            return
        await ws.accept()
        try:
            cursor = max(after, 0)
            while True:
                s = store()
                try:
                    batch = [e for e in s.events(rid) if e.seq > cursor]
                finally:
                    s.db.close()
                for event in batch:
                    await ws.send_json(event.model_dump())
                    cursor = event.seq
                await ws.send_json({"heartbeat": True, "cursor": cursor})
                await asyncio.sleep(0.15)
        except (WebSocketDisconnect, RuntimeError):
            return

    @app.get("/api/knowledge", dependencies=[Depends(authenticate)])
    def knowledge(q: str = "average") -> dict[str, object]:
        if len(q) > 1000:
            raise HTTPException(422, "Query too long")
        try:
            citations = retrieve(repo, q, 24000)
            return {
                "strategy": "AST + lexical baseline",
                "repository": repo.name,
                "results": [e.model_dump() for e in citations],
            }
        except ValueError as exc:
            return {
                "strategy": "AST + lexical baseline",
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
                    "log": log,
                    "mode": "hosted",
                    "policy": FleetPolicy.model_validate(s.settings()).model_dump(),
                    "head_sha": check.get("head_sha"),
                },
            )
            with s.db:
                s.db.execute("INSERT INTO deliveries VALUES(?,?)", (delivery, rid))
                s.db.execute("INSERT INTO jobs VALUES(?,'queued')", (rid,))
            return {"id": rid}
        finally:
            s.db.close()

    output = Path(__file__).resolve().parents[1] / "web" / "out"
    if output.exists():
        app.mount("/", StaticFiles(directory=output, html=True), name="dashboard")
    return app
