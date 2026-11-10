# IRONCLAD · Autonomous Code Guardian

**Phase 1: runnable CLI, typed agent graph, append-only events, cited diagnosis, guarded patch proposals.**

This implements the first delivery phase of the supplied specification. It is a development foundation, not a production autonomous repair service. The default demo is deterministic and clearly identified. Hosted mode uses your configured model API. No repository code is executed by the agents, no files in the target repository are modified, and no PR is opened in this phase.

## Repository structure

```text
ironclad/
  schema.py       typed messages, agent outputs and policies
  store.py        durable SQLite event log and checkpoint storage
  repository.py   AST chunks, retrieval and guarded diff creation
  engine.py       explicit Watcher → Diagnostician → Surgeon graph
  model.py        hosted model adapter with structured-output retry
  bus.py          optional idempotent Redis Streams relay
  cli.py          run, resume, replay and export
examples/
  broken_repo/    deliberately failing Python project
  failure.log
design/tokens.css
docs/message.schema.json
tests/test_engine.py
pyproject.toml
```

## Quick start (Python 3.12+)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m ironclad.cli run --repo examples/broken_repo --log examples/failure.log
```

Copy the run ID printed on the first line:

```bash
python -m ironclad.cli replay RUN_ID
python -m ironclad.cli resume RUN_ID
python -m ironclad.cli export RUN_ID --output proposed.patch
```

The fixture declares that `average([])` must return `0.0`. The demo emits the three typed agent events and a unified diff adding that guard. The repository is unchanged. Patch metadata explicitly says `NOT_RUN` and `PROPOSAL_ONLY`. To inspect the fix yourself, use a disposable copy of the fixture, apply the patch with `git apply`, and run pytest there.

For a different policy, create a JSON file using the fields in `Guardrails` and pass `--policy policy.json`. Unknown keys and out-of-range settings are rejected.

## Hosted model mode

Set the environment variables listed in `.env.example` in your terminal. The file is documentation, not automatically loaded. Supply your provider's actual input/output prices and a compatible chat-completions model. Run:

```bash
python -m ironclad.cli run --repo /path/to/python/repo --log failure.log --mode hosted
```

This sends selected repository function/class text and failure logs to the configured model provider. Use repositories/logs you can share with that provider. No GitHub or model credentials belong inside the target repository. Denied paths are excluded, but arbitrary secrets inside permitted Python source are not automatically detected: redact those before hosted use.

Responses are validated against Pydantic schemas; malformed JSON gets one schema-directed retry. Each attempted request reserves a conservative estimated cost before sending. No network retry is automatic after an unknown provider outcome. Timeouts and provider failures escalate. No hosted call was made during delivery verification.

## Architectural decisions

**Graph instead of a linear ad-hoc agent loop:** the transition table is explicit and bounded. Each node consumes persisted typed predecessor output. Phase one is acyclic; there is no correction loop to detect. Later verification cycles must carry attempt counters and repeat-state hashes before being introduced.

**Persistence:** SQLite WAL provides a zero-service local first phase. State is reconstructed from ordered immutable events. The unique `(run_id, seq)` key prevents duplicate steps. Run IDs represent independent submissions; repeated log submissions are not automatically deduplicated. Use one CLI writer per run. Concurrent multi-worker execution requires leases and atomic transition claims before production use.

**Redis:** `RedisBus` mirrors committed events to per-run Streams using sequence-derived IDs. Install `.[redis]`, instantiate `redis.Redis.from_url(...)`, and call `RedisBus(client).publish(event)` for events read from `Store`. It is an optional relay adapter, not yet a production worker transport. SQLite polling/replay is the default local event bus. PostgreSQL, pgvector, and durable worker dispatch are later-phase work; SQLite is an intentional runnable-first deviation.

**Retrieval:** bounded AST-level Python function/class chunks ranked by lexical overlap. Citations are validated against retrieved evidence. This is a baseline, not BM25/vector hybrid search. No embeddings or invented vector-search metrics are claimed.

**Cost:** all requests have output and call caps. Preflight reservations depend on accurate configured provider prices and conventional byte-tokenized input accounting. This is a conservative application estimate, not a billing guarantee; provider billing limits remain necessary for a hard financial ceiling. Demo mode costs nothing. Interrupted hosted runs escalate rather than silently refreshing their budget; a new run requires an explicit new invocation. A crash before the first committed event is a remaining accounting limitation.

**Untrusted generated code:** phase one generates diffs and parses Python syntax; it never imports, runs, or installs target code. Docker execution with CPU, memory, network and time limits is not implemented yet and must precede autonomous verification. AST parsing is not a security sandbox.

**Replay and trust:** replay displays recorded outputs and evidence without making new model calls. It reconstructs recorded agent steps, not a historical filesystem snapshot or hidden model reasoning. We persist concise evidence-based rationales, not private chain-of-thought.

**Autonomy versus blast radius:** deny dot-directories, infrastructure, migrations, symlinks, credentials and lockfiles; restrict proposals to cited Python files and five files maximum. Require exact unique edit matches, syntactically valid output and a nonempty patch. The repository is never mutated. Human review and later isolated tests are required before using a proposal.

## Tests

```bash
python -m pytest --cov=ironclad --cov-report=term-missing
python -m ruff check ironclad tests
python -m mypy ironclad
```

Integration tests apply a generated diff only to a disposable fixture and run its actual tests. Additional tests cover immutable history, checkpoint recovery, terminal-run idempotency, path traversal, denied paths, symlinks, malformed edits, input policies and budget stops. `VALIDATION.md` records the actual checks run at delivery.

## Next phases

1. Add Verifier with fresh restricted Docker containers, baseline regression comparison, bounded correction attempts and escalation.
2. Add PostgreSQL/pgvector, Redis workers with leases, provider request accounting and hardened redaction.
3. Add FastAPI/WebSocket telemetry and Next.js mission-control UI using the included design tokens.
4. Add authenticated GitHub webhooks and a restricted installation token for draft PR creation.
5. Add the remaining replay/review/knowledge/settings screens, observability and load tests.

The seven-screen dashboard, GitHub integration, live WebSockets, 500-client load target, 80% orchestration/guardrail coverage target and production security review are not claimed complete by this phase-one delivery.
