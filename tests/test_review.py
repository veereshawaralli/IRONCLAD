from pathlib import Path
from uuid import uuid4

import pytest

from ironclad.fleet import Fleet
from ironclad.review import Review
from ironclad.schema import FleetPolicy, Verification
from ironclad.store import Store


class Verifier:
    def verify(self, repo, proposal):
        return Verification(
            passed=True,
            baseline_failures=["test_empty"],
            remaining_failures=[],
            checks={"tests": True},
            output="trusted test double",
        )


class Publisher:
    def __init__(self):
        self.calls = 0

    def publish(self, *args):
        self.calls += 1
        return "https://github.com/example/repo/pull/1"


def test_approval_publish_idempotency(tmp_path):
    s = Store(tmp_path / "events.db")
    rid = uuid4().hex
    s.begin(
        rid,
        {
            "repo": str(Path("examples/broken_repo").resolve()),
            "mode": "demo",
            "log": "ZeroDivisionError",
            "policy": FleetPolicy().model_dump(),
        },
    )
    Fleet(s, Verifier()).execute(rid)
    review = Review(s)
    publisher = Publisher()
    with pytest.raises(ValueError, match="Approve"):
        review.publish(rid, publisher)
    with pytest.raises(ValueError, match="confirmation"):
        review.approve(rid, False)
    review.approve(rid, True)
    review.approve(rid, True)
    assert review.publish(rid, publisher) == review.publish(rid, publisher)
    assert publisher.calls == 1
    assert len([e for e in s.events(rid) if e.kind == "approved"]) == 1


def test_simulation_cannot_approve(tmp_path):
    s = Store(tmp_path / "events.db")
    s.begin("sim", {"mode": "simulation"})
    with pytest.raises(ValueError, match="Simulation"):
        Review(s).approve("sim", True)
