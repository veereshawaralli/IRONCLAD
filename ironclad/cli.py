import argparse
from pathlib import Path

from .engine import Engine
from .schema import Guardrails
from .store import Store


def main() -> None:
    parser = argparse.ArgumentParser(
        description="IRONCLAD · autonomous codebase guardian · phase 1"
    )
    parser.add_argument("--db", type=Path, default=Path(".ironclad/events.db"))
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--repo", type=Path, required=True)
    run.add_argument("--log", type=Path, required=True)
    run.add_argument("--mode", choices=["demo", "hosted"], default="demo")
    run.add_argument("--policy", type=Path)
    for name in ("replay", "resume", "export"):
        sub = commands.add_parser(name)
        sub.add_argument("run_id")
        if name == "export":
            sub.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    store = Store(args.db)
    engine = Engine(store)
    if args.command == "run":
        policy = (
            Guardrails.model_validate_json(args.policy.read_text())
            if args.policy
            else Guardrails()
        )
        run_id = engine.start(args.repo, args.log.read_text(), args.mode, policy)
        print("RUN", run_id)
    else:
        run_id = args.run_id
        store.input(run_id)
        if args.command == "resume":
            engine.resume(run_id)
    events = store.events(run_id)
    if args.command == "export":
        if not events or events[-1].kind != "proposal":
            parser.error("Run has no patch proposal")
        args.output.write_text(str(events[-1].payload["diff"]))
        print("Exported unverified proposal:", args.output)
    else:
        for event in events:
            print(event.model_dump_json(indent=2))
    if events and events[-1].kind == "escalated":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
