"""Actual demo-to-Docker-verifier smoke check, used in CI."""
from pathlib import Path
from tempfile import TemporaryDirectory
from ironclad.fleet import Fleet
from ironclad.schema import FleetPolicy
from ironclad.sandbox import DockerSandbox
from ironclad.store import Store

with TemporaryDirectory() as temp:
    store=Store(Path(temp)/'events.db')
    rid='0123456789abcdef0123456789abcdef'
    store.begin(rid,{'repo':str(Path('examples/broken_repo').resolve()),'log':'ZeroDivisionError in average','mode':'demo','policy':FleetPolicy().model_dump()})
    Fleet(store,DockerSandbox()).execute(rid)
    events=store.events(rid)
    for event in events:
        print(event.model_dump_json())
    assert events[-1].kind=='report','Isolated demo repair did not pass'
