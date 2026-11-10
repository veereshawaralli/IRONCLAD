import time
from typing import cast

from .fleet import Fleet
from .github import GitHub
from .schema import Agent, Proposal
from .store import Store


class Review:
    def __init__(self, store: Store):
        self.store = store

    def approve(self, rid: str, confirmed: bool) -> None:
        if not confirmed:
            raise ValueError("Explicit diff review confirmation required")
        data = self.store.input(rid)
        events = self.store.events(rid)
        if data.get("mode") == "simulation":
            raise ValueError("Simulation runs cannot be approved or published")
        if not events or events[-1].kind not in {"report", "approved", "pull_request"}:
            raise ValueError("A verified reporter result is required")
        verifications = [e for e in events if e.kind == "verification"]
        if not verifications or verifications[-1].payload.get("passed") is not True:
            raise ValueError("Latest verification must pass")
        if any(e.kind == "approved" for e in events):
            return
        Fleet(self.store, None).emit(
            rid, Agent.SUPERVISOR, "approved", {"reviewed": True}, time.monotonic()
        )

    def publish(self, rid: str, github: GitHub) -> str:
        events = self.store.events(rid)
        existing = [e for e in events if e.kind == "pull_request"]
        if existing:
            return str(existing[-1].payload["url"])
        if not any(e.kind == "approved" for e in events):
            raise ValueError("Approve the reviewed patch first")
        if self.store.input(rid).get("mode") == "simulation":
            raise ValueError("Simulation publication blocked")
        # Serializes one publisher per run. Ambiguous failures require explicit retry.
        with self.store.db:
            self.store.db.execute(
                "CREATE TABLE IF NOT EXISTS publications(run_id TEXT PRIMARY KEY,status TEXT NOT NULL)"
            )
            prior = self.store.db.execute(
                "SELECT status FROM publications WHERE run_id=?", (rid,)
            ).fetchone()
            if prior and prior[0] == "publishing":
                raise ValueError(
                    "Publication in progress or interrupted; inspect GitHub before retrying"
                )
            self.store.db.execute(
                "INSERT INTO publications VALUES(?,'publishing') ON CONFLICT(run_id) DO UPDATE SET status='publishing'",
                (rid,),
            )
        try:
            patch = [e for e in events if e.kind == "proposal"][-1].payload
            proposal = Proposal.model_validate(
                {k: patch[k] for k in ["summary", "edits"]}
            )
            report = [e for e in events if e.kind == "report"][-1].payload
            url = github.publish(
                rid, proposal, cast(dict[str, str], patch["baseline_sha256"]), report
            )
            Fleet(self.store, None).emit(
                rid,
                Agent.REPORTER,
                "pull_request",
                {"url": url, "draft": True},
                time.monotonic(),
            )
            with self.store.db:
                self.store.db.execute(
                    "UPDATE publications SET status='complete' WHERE run_id=?", (rid,)
                )
            return url
        except Exception:
            with self.store.db:
                self.store.db.execute(
                    "UPDATE publications SET status='retryable' WHERE run_id=?", (rid,)
                )
            raise
