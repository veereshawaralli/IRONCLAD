"""Opt-in real model → isolated tests → draft PR acceptance, never auto-merge."""

import os
import tempfile
from pathlib import Path
from uuid import uuid4

from ironclad.fleet import Fleet
from ironclad.github import GitHub
from ironclad.review import Review
from ironclad.sandbox import DockerSandbox
from ironclad.schema import FleetPolicy
from ironclad.store import Store

required = [
    "IRONCLAD_API_KEY",
    "IRONCLAD_MODEL",
    "IRONCLAD_INPUT_USD_PER_MILLION",
    "IRONCLAD_OUTPUT_USD_PER_MILLION",
    "IRONCLAD_GITHUB_TOKEN",
    "IRONCLAD_GITHUB_REPO",
]
missing = [name for name in required if not os.environ.get(name)]
if missing:
    raise SystemExit("Acceptance blocked: configure " + ", ".join(missing))
if os.environ.get("IRONCLAD_ACCEPTANCE_APPROVE") != "1":
    raise SystemExit(
        "Acceptance publication must be explicitly enabled in the test environment"
    )
with tempfile.TemporaryDirectory() as temp:
    store = Store(Path(temp) / "acceptance.db")
    rid = uuid4().hex
    repo = Path(os.environ.get("IRONCLAD_REPO", "examples/broken_repo")).resolve()
    store.begin(
        rid,
        {
            "repo": str(repo),
            "mode": "hosted",
            "log": "ZeroDivisionError in stats.py average([]). The function contract requires 0.0 for empty input.",
            "policy": FleetPolicy(
                dollar_budget=1, max_model_calls=6, max_output_tokens=1500
            ).model_dump(),
        },
    )
    Fleet(store, DockerSandbox()).execute(rid)
    events = store.events(rid)
    for event in events:
        print(event.model_dump_json())
    if not events or events[-1].kind != "report":
        raise SystemExit("Real hosted acceptance did not reach passing verification")
    review = Review(store)
    review.approve(rid, True)
    url = review.publish(rid, GitHub())
    print("Draft PR:", url)
    store.db.close()
