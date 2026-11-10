"""Single worker per installation; a restarted running job escalates instead of replaying effects."""

import os
import time
from pathlib import Path

from .fleet import Fleet
from .sandbox import DockerSandbox
from .store import Store


def main() -> None:
    store = Store(Path(os.environ.get("IRONCLAD_DB", ".ironclad/events.db")))
    fleet = Fleet(store, DockerSandbox())
    for (rid,) in store.db.execute(
        "SELECT id FROM jobs WHERE status='running'"
    ).fetchall():
        fleet.emit(
            rid,
            __import__("ironclad.schema", fromlist=["Agent"]).Agent.SUPERVISOR,
            "escalated",
            {"reason": "Worker interrupted; review recorded state before a new run"},
            time.monotonic(),
        )
        store.finish(rid)
    while True:
        rid = store.claim()
        if rid:
            fleet.execute(rid)
            store.finish(rid)
        else:
            time.sleep(0.5)


if __name__ == "__main__":
    main()
