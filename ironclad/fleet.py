"""Bounded graph: observe → diagnose → propose → verify → reflect/report."""

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .knowledge import retrieve
from .model import HostedModel
from .redaction import redact
from .repository import render_patch
from .resilience import ProviderError
from .schema import (
    Agent,
    Diagnosis,
    FleetPolicy,
    Incident,
    Message,
    Proposal,
    Verification,
)
from .store import Store


class Sandbox(Protocol):
    def verify(self, repo: Path, proposal: Proposal) -> Verification: ...


class Fleet:
    def __init__(self, store: Store, sandbox: Sandbox | None):
        self.store, self.sandbox = store, sandbox

    def emit(
        self,
        run_id: str,
        agent: Agent,
        kind: str,
        payload: dict[str, object],
        started: float,
    ) -> None:
        self.store.record(
            Message.model_validate(
                {
                    "run_id": run_id,
                    "seq": 1,
                    "agent": agent,
                    "kind": kind,
                    "payload": payload,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "duration_ms": int((time.monotonic() - started) * 1000),
                }
            ),
            unique_kind=kind in {"approved", "pull_request"},
        )

    def execute(self, run_id: str) -> None:
        started = time.monotonic()
        try:
            data = self.store.input(run_id)
            previous = self.store.events(run_id)
            if previous and previous[-1].kind in {
                "report",
                "escalated",
                "pull_request",
            }:
                return
            if previous:
                raise ValueError(
                    "Interrupted fleet runs are not replayed automatically; submit a new budgeted run"
                )
            repo = Path(str(data["repo"]))
            log = redact(str(data["log"]))
            policy = FleetPolicy.model_validate(data.get("policy", {}))
            if len(log) > policy.max_input_chars:
                raise ValueError("Input limit exceeded")
            model = (
                HostedModel(
                    policy.max_model_calls,
                    policy.dollar_budget,
                    policy.max_output_tokens,
                    reserve=lambda amount: self.store.reserve(
                        run_id, amount, policy.dollar_budget, policy.max_model_calls
                    ),
                )
                if data.get("mode") == "hosted"
                else None
            )
            self.emit(
                run_id,
                Agent.WATCHER,
                "incident",
                Incident(
                    severity="high",
                    summary=(log.splitlines() or ["Failure"])[-1][:1000],
                    fingerprint=hashlib.sha256(log.encode()).hexdigest(),
                ).model_dump(),
                started,
            )
            seen: set[str] = set()
            for attempt in range(1, policy.max_attempts + 1):
                if len(self.store.events(run_id)) + 4 > policy.max_steps:
                    raise ValueError("Graph step cap reached")
                step = time.monotonic()
                evidence = retrieve(
                    repo,
                    log,
                    policy.max_input_chars - len(log),
                    self.store,
                    run_id,
                    policy.dollar_budget,
                    policy.max_model_calls,
                )
                if model:
                    diagnosis = model.generate(
                        Diagnosis,
                        json.dumps(
                            {"log": log, "evidence": [e.model_dump() for e in evidence]}
                        ),
                    )
                    if any(e not in evidence for e in diagnosis.evidence):
                        raise ValueError("Ungrounded evidence rejected")
                else:
                    matches = [
                        e for e in evidence if "sum(values) / len(values)" in e.text
                    ]
                    if not matches or "ZeroDivisionError" not in log:
                        raise ValueError("Demo mode supports the bundled fixture only")
                    diagnosis = Diagnosis(
                        hypothesis="Empty input violates the zero-result fixture contract",
                        confidence=0.98,
                        evidence=[matches[0]],
                    )
                self.emit(
                    run_id,
                    Agent.DIAGNOSTICIAN,
                    "diagnosis",
                    {**diagnosis.model_dump(), "attempt": attempt},
                    step,
                )
                step = time.monotonic()
                if model:
                    proposal = model.generate(
                        Proposal,
                        diagnosis.model_dump_json()
                        + "\nPrevious verifier feedback: "
                        + log,
                    )
                else:
                    proposal = Proposal.model_validate(
                        {
                            "summary": "Guard empty input",
                            "edits": [
                                {
                                    "path": diagnosis.evidence[0].path,
                                    "old": "    return sum(values) / len(values)",
                                    "new": "    if not values:\n        return 0.0\n    return sum(values) / len(values)",
                                    "rationale": "Preserve the documented empty-input contract",
                                }
                            ],
                        }
                    )
                if any(
                    e.path not in {d.path for d in diagnosis.evidence}
                    for e in proposal.edits
                ):
                    raise ValueError("Out-of-scope proposal")
                diff, hashes = render_patch(repo, proposal, policy.max_files)
                fingerprint = hashlib.sha256(diff.encode()).hexdigest()
                if fingerprint in seen:
                    raise ValueError("Repeated patch cycle detected")
                seen.add(fingerprint)
                self.emit(
                    run_id,
                    Agent.SURGEON,
                    "proposal",
                    {
                        **proposal.model_dump(),
                        "diff": diff,
                        "baseline_sha256": hashes,
                        "attempt": attempt,
                    },
                    step,
                )
                step = time.monotonic()
                if self.sandbox is None:
                    raise ValueError("No isolated verifier configured")
                result = self.sandbox.verify(repo, proposal)
                self.emit(
                    run_id,
                    Agent.VERIFIER,
                    "verification",
                    {**result.model_dump(), "attempt": attempt},
                    step,
                )
                if result.passed:
                    self.emit(
                        run_id,
                        Agent.REPORTER,
                        "report",
                        {
                            "title": "fix: " + proposal.summary,
                            "body": "## Incident\n"
                            + diagnosis.hypothesis
                            + "\n\n## Change\n"
                            + proposal.summary
                            + "\n\n## Verification\n"
                            + json.dumps(result.checks),
                            "risk": "Human review required; no auto-merge",
                            "status": "awaiting_review",
                        },
                        time.monotonic(),
                    )
                    return
                log = (log + "\nVerifier feedback: " + result.model_dump_json())[
                    -policy.max_input_chars // 2 :
                ]
            raise ValueError("Self-correction attempt limit reached")
        except Exception as exc:  # noqa: BLE001 -- workflow termination boundary
            if isinstance(exc, ProviderError):
                self.emit(
                    run_id,
                    Agent.SUPERVISOR,
                    "escalated",
                    {
                        "reason": str(exc),
                        "error_kind": exc.kind,
                        "retryable": exc.retryable,
                    },
                    started,
                )
                return
            reason = (
                str(exc)
                if type(exc) is ValueError
                else "Tool failure: " + type(exc).__name__
            )
            self.emit(
                run_id, Agent.SUPERVISOR, "escalated", {"reason": reason}, started
            )
