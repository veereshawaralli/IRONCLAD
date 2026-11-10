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
