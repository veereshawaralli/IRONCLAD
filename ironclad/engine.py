import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from .model import HostedModel
from .repository import render_patch, retrieve
from .schema import Agent, Diagnosis, Guardrails, Incident, Message, Proposal
from .store import Store


class Engine:
    def __init__(self, store: Store):
        self.store = store

    def start(self, repo: Path, log: str, mode: str, policy: Guardrails) -> str:
        if len(log) > policy.max_input_chars:
            raise ValueError("Log exceeds input limit")
        run_id = uuid4().hex
        self.store.begin(
            run_id,
            {
                "repo": str(repo.resolve()),
                "log": log,
                "mode": mode,
                "policy": policy.model_dump(),
            },
        )
        self.resume(run_id)
        return run_id

    def resume(self, run_id: str) -> None:
        data = self.store.input(run_id)
        events = self.store.events(run_id)
        if events and events[-1].kind in ("proposal", "escalated"):
            return
        policy = Guardrails.model_validate(data["policy"])
        repo = Path(str(data["repo"]))
        log = str(data["log"])
        # Hosted calls cannot safely be replayed after an unknown network outcome.
        # Refuse crash recovery rather than risk charging a fresh budget.
        model = None
        try:
            if data["mode"] == "hosted":
                if events:
                    raise ValueError(
                        "Interrupted hosted run requires a new explicitly budgeted run"
                    )
                model = HostedModel(
                    policy.max_model_calls,
                    policy.dollar_budget,
                    policy.max_output_tokens,
                )
            graph: list[tuple[Agent, Literal["incident", "diagnosis", "proposal"]]] = [
                (Agent.WATCHER, "incident"),
                (Agent.DIAGNOSTICIAN, "diagnosis"),
                (Agent.SURGEON, "proposal"),
            ]
            output: Incident | Diagnosis | Proposal
            for agent, kind in graph:
                if any(e.agent == agent for e in events):
                    continue
                if len(events) >= policy.max_steps:
                    raise ValueError("Step budget exhausted")
                before = time.monotonic()
                if agent == Agent.WATCHER:
                    output = Incident(
                        severity="high" if "Error" in log else "medium",
                        summary=(log.splitlines() or ["Failure reported"])[-1][:1000]
                        or "Failure reported",
                        fingerprint=hashlib.sha256(log.encode()).hexdigest(),
                    )
                    payload = output.model_dump()
                elif agent == Agent.DIAGNOSTICIAN:
                    evidence = retrieve(repo, log, policy.max_input_chars - len(log))
                    if model:
                        output = model.generate(
                            Diagnosis,
                            json.dumps(
                                {
                                    "log": log,
                                    "evidence": [e.model_dump() for e in evidence],
                                }
                            ),
                        )
                        if any(e not in evidence for e in output.evidence):
                            raise ValueError(
                                "Diagnosis cited evidence outside retrieved context"
                            )
                    else:
                        match = [
                            e for e in evidence if "sum(values) / len(values)" in e.text
                        ]
                        if not match or "ZeroDivisionError" not in log:
                            raise ValueError(
                                "Demo supports only the supplied average/empty-input fixture; use hosted mode for other issues"
                            )
                        output = Diagnosis(
                            hypothesis="average divides by zero for empty input; fixture contract expects 0.0",
                            confidence=0.98,
                            evidence=[match[0]],
                        )
                    payload = output.model_dump()
                else:
                    diagnosis = Diagnosis.model_validate(events[-1].payload)
                    if model:
                        output = model.generate(Proposal, diagnosis.model_dump_json())
                    else:
                        output = Proposal.model_validate(
                            {
                                "summary": "Handle empty input before division",
                                "edits": [
                                    {
                                        "path": diagnosis.evidence[0].path,
                                        "old": "    return sum(values) / len(values)",
                                        "new": "    if not values:\n        return 0.0\n    return sum(values) / len(values)",
                                        "rationale": "Empty input is defined to return 0.0 by the demo contract.",
                                    }
                                ],
                            }
                        )
                    allowed = {e.path for e in diagnosis.evidence}
                    if any(e.path not in allowed for e in output.edits):
                        raise ValueError("Edit outside cited evidence")
                    diff, hashes = render_patch(repo, output, policy.max_files)
                    payload = {
                        **output.model_dump(),
                        "diff": diff,
                        "baseline_sha256": hashes,
                        "verification": "NOT_RUN",
                        "approval": "PROPOSAL_ONLY",
                    }
                event = Message(
                    run_id=run_id,
                    seq=len(events) + 1,
                    agent=agent,
                    kind=kind,
                    payload=payload,
                    timestamp=datetime.now(UTC).isoformat(),
                    duration_ms=int((time.monotonic() - before) * 1000),
                )
                self.store.append(event)
                events.append(event)
        except Exception as error:  # noqa: BLE001 -- terminal boundary records tool failures
            # Do not persist provider exceptions, headers, secrets or raw responses.
            reason = (
                str(error)
                if isinstance(error, ValueError)
                else "Tool/provider failure: " + type(error).__name__
            )
            self.store.append(
                Message(
                    run_id=run_id,
                    seq=len(events) + 1,
                    agent=Agent.SUPERVISOR,
                    kind="escalated",
                    payload={"reason": reason},
                    timestamp=datetime.now(UTC).isoformat(),
                    duration_ms=0,
                )
            )
