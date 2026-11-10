from pathlib import Path
from uuid import uuid4

from ironclad.fleet import Fleet
from ironclad.sandbox import DockerSandbox
from ironclad.schema import FleetPolicy, Verification
from ironclad.store import Store


class FakeSandbox:
    def __init__(self, passed=True):
        self.passed = passed

    def verify(self, repo, proposal):
        return Verification(
            passed=self.passed,
            baseline_failures=["test_empty"],
            remaining_failures=[] if self.passed else ["test_empty"],
            checks={"tests": self.passed},
            output="fixture result",
        )


def run(tmp_path, sandbox):
    store = Store(tmp_path / "events.db")
    run_id = uuid4().hex
    store.begin(
        run_id,
        {
            "repo": str(Path("examples/broken_repo").resolve()),
            "log": "ZeroDivisionError in average",
            "mode": "demo",
            "policy": FleetPolicy().model_dump(),
        },
    )
    Fleet(store, sandbox).execute(run_id)
    return store, run_id


def test_fleet_verification_report(tmp_path):
    store, rid = run(tmp_path, FakeSandbox())
    assert [e.kind for e in store.events(rid)] == [
        "incident",
        "diagnosis",
        "proposal",
        "verification",
        "report",
    ]


def test_repeated_patch_escalates(tmp_path):
    store, rid = run(tmp_path, FakeSandbox(False))
    assert store.events(rid)[-1].kind == "escalated"
    assert "cycle" in store.events(rid)[-1].payload["reason"]


def test_no_host_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    import pytest

    with pytest.raises(ValueError, match="Docker"):
        DockerSandbox().run(tmp_path)


def test_durable_budget(tmp_path):
    import pytest

    store = Store(tmp_path / "events.db")
    store.reserve("run", 0.3, 0.5, 3)
    reopened = Store(tmp_path / "events.db")
    with pytest.raises(ValueError, match="budget"):
        reopened.reserve("run", 0.3, 0.5, 3)


def test_terminal_run_is_not_executed_twice(tmp_path):
    store, rid = run(tmp_path, FakeSandbox())
    before = store.events(rid)
    Fleet(store, FakeSandbox()).execute(rid)
    assert store.events(rid) == before


def test_hosted_correction_uses_verifier_feedback(tmp_path, monkeypatch):
    from ironclad.knowledge import retrieve
    from ironclad.schema import Diagnosis, Proposal

    evidence = next(
        e
        for e in retrieve(Path("examples/broken_repo"), "average", 24000)
        if e.path == "stats.py"
    )

    class Model:
        def __init__(self):
            self.attempt = 0

        def generate(self, schema, content):
            if schema is Diagnosis:
                return Diagnosis(
                    hypothesis="Empty input bug", confidence=0.95, evidence=[evidence]
                )
            self.attempt += 1
            new = (
                "    return 1.0"
                if self.attempt == 1
                else "    if not values:\n        return 0.0\n    return sum(values) / len(values)"
            )
            if self.attempt == 2:
                assert "Verifier feedback" in content
            return Proposal.model_validate(
                {
                    "summary": "guard input",
                    "edits": [
                        {
                            "path": "stats.py",
                            "old": "    return sum(values) / len(values)",
                            "new": new,
                            "rationale": "fixture contract",
                        }
                    ],
                }
            )

    class Verifier:
        def __init__(self):
            self.attempt = 0

        def verify(self, repo, proposal):
            self.attempt += 1
            return Verification(
                passed=self.attempt == 2,
                baseline_failures=["empty"],
                remaining_failures=[] if self.attempt == 2 else ["mean"],
                checks={"tests": self.attempt == 2},
                output="retry with correct average semantics",
            )

    model = Model()
    monkeypatch.setattr("ironclad.fleet.HostedModel", lambda *args, **kwargs: model)
    store = Store(tmp_path / "hosted.db")
    rid = uuid4().hex
    store.begin(
        rid,
        {
            "repo": str(Path("examples/broken_repo").resolve()),
            "mode": "hosted",
            "log": "ZeroDivisionError in average",
            "policy": FleetPolicy().model_dump(),
        },
    )
    Fleet(store, Verifier()).execute(rid)
    assert store.events(rid)[-1].kind == "report"
    assert model.attempt == 2
