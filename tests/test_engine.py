import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from ironclad.engine import Engine
from ironclad.repository import render_patch, retrieve, safe_file
from ironclad.schema import Guardrails, Proposal
from ironclad.store import Store

FIXTURES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def setup(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURES / "broken_repo", repo)
    store = Store(tmp_path / "events.db")
    return repo, store, Engine(store)


def test_pipeline_and_real_patch(setup, tmp_path):
    repo, store, engine = setup
    original = (repo / "stats.py").read_text()
    run_id = engine.start(
        repo, (FIXTURES / "failure.log").read_text(), "demo", Guardrails()
    )
    events = store.events(run_id)
    assert [e.kind for e in events] == ["incident", "diagnosis", "proposal"]
    assert events[-1].payload["verification"] == "NOT_RUN"
    assert (repo / "stats.py").read_text() == original
    patch = tmp_path / "fix.patch"
    patch.write_text(events[-1].payload["diff"])
    subprocess.run(["git", "apply", str(patch)], cwd=repo, check=True)
    subprocess.run(["python", "-m", "pytest", "-q", str(repo)], cwd=repo, check=True)
    engine.resume(run_id)
    assert store.events(run_id) == events


def test_resume_from_checkpoint(setup):
    repo, store, engine = setup
    first = engine.start(
        repo, (FIXTURES / "failure.log").read_text(), "demo", Guardrails()
    )
    data = store.input(first)
    store.begin("recovered", data)
    store.append(store.events(first)[0].model_copy(update={"run_id": "recovered"}))
    Engine(Store(Path(store.db.execute("PRAGMA database_list").fetchone()[2]))).resume(
        "recovered"
    )
    assert [e.kind for e in store.events("recovered")] == [
        "incident",
        "diagnosis",
        "proposal",
    ]


@pytest.mark.parametrize(
    "name",
    [
        "../escape.py",
        "/etc/passwd",
        ".env",
        "infra/app.py",
        ".github/workflows/a.py",
        "secret.py",
        "poetry.lock",
    ],
)
def test_denied_paths(setup, name):
    with pytest.raises(ValueError):
        safe_file(setup[0], name)


def test_symlink_denied(setup, tmp_path):
    repo, _, _ = setup
    target = tmp_path / "outside.py"
    target.write_text("private = 1")
    (repo / "linked.py").symlink_to(target)
    with pytest.raises(ValueError):
        safe_file(repo, "linked.py")


def test_step_limit_escalates(setup):
    repo, store, engine = setup
    run_id = engine.start(repo, "ZeroDivisionError", "demo", Guardrails(max_steps=1))
    assert store.events(run_id)[-1].kind == "escalated"


def test_unknown_failure_escalates(setup):
    repo, store, engine = setup
    run_id = engine.start(
        repo, "TypeError: unsupported operation", "demo", Guardrails()
    )
    assert store.events(run_id)[-1].kind == "escalated"


def test_no_eligible_evidence(tmp_path):
    with pytest.raises(ValueError):
        retrieve(tmp_path, "failure", 10000)


def test_noop_and_invalid_edits(setup):
    repo, _, _ = setup
    for old, new in [
        ("missing", "x"),
        ("return sum(values) / len(values)", "return ("),
    ]:
        proposal = Proposal(
            summary="test",
            edits=[{"path": "stats.py", "old": old, "new": new, "rationale": "test"}],
        )
        with pytest.raises((ValueError, SyntaxError)):
            render_patch(repo, proposal, 5)


def test_append_only(setup):
    repo, store, engine = setup
    engine.start(repo, "ZeroDivisionError", "demo", Guardrails())
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute("DELETE FROM events")


def test_policy_validation():
    with pytest.raises(ValueError):
        Guardrails(max_files=6)


def test_hosted_budget_before_network(monkeypatch):
    from ironclad.model import HostedModel

    monkeypatch.setenv("IRONCLAD_INPUT_USD_PER_MILLION", "100")
    monkeypatch.setenv("IRONCLAD_OUTPUT_USD_PER_MILLION", "100")
    with pytest.raises(ValueError, match="budget"):
        HostedModel(2, 0.0001, 1200).generate(Proposal, "test")


def test_hosted_schema_retry_and_real_pipeline(setup, monkeypatch):
    import io
    import json
    import urllib.request

    repo, store, engine = setup
    for key, value in {
        "IRONCLAD_INPUT_USD_PER_MILLION": "1",
        "IRONCLAD_OUTPUT_USD_PER_MILLION": "1",
        "IRONCLAD_MODEL": "mock-model",
        "IRONCLAD_API_KEY": "mock-key",
    }.items():
        monkeypatch.setenv(key, value)
    evidence = retrieve(repo, "ZeroDivisionError average", 24000)[0]
    responses = iter(
        [
            "invalid json",
            __import__("ironclad.schema", fromlist=["Diagnosis"])
            .Diagnosis(
                hypothesis="Empty input divides by zero",
                confidence=0.9,
                evidence=[evidence],
            )
            .model_dump_json(),
            Proposal.model_validate(
                {
                    "summary": "Guard empty input",
                    "edits": [
                        {
                            "path": "stats.py",
                            "old": "    return sum(values) / len(values)",
                            "new": "    if not values:\n        return 0.0\n    return sum(values) / len(values)",
                            "rationale": "Fixture contract requires zero for empty input",
                        }
                    ],
                }
            ).model_dump_json(),
        ]
    )

    def reply(*args, **kwargs):
        return io.BytesIO(
            json.dumps(
                {"choices": [{"message": {"content": next(responses)}}]}
            ).encode()
        )

    monkeypatch.setattr(urllib.request, "urlopen", reply)
    run_id = engine.start(repo, "ZeroDivisionError average", "hosted", Guardrails())
    assert store.events(run_id)[-1].kind == "proposal"


def test_redis_relay_idempotency(setup):
    from ironclad.bus import RedisBus

    repo, store, engine = setup
    run_id = engine.start(repo, "ZeroDivisionError", "demo", Guardrails())

    class FakeRedis:
        def __init__(self):
            self.rows = {}

        def xrange(self, stream, min, max):
            return [self.rows[(stream, min)]] if (stream, min) in self.rows else []

        def xadd(self, stream, fields, id):
            self.rows[(stream, id)] = fields

    client = FakeRedis()
    bus = RedisBus(client)
    for event in store.events(run_id):
        bus.publish(event)
        bus.publish(event)
    assert len(client.rows) == 3


def test_input_limit_and_missing_run(setup):
    repo, store, engine = setup
    with pytest.raises(ValueError, match="input limit"):
        engine.start(repo, "x" * 24001, "demo", Guardrails())
    with pytest.raises(ValueError, match="Unknown run"):
        store.input("missing")
