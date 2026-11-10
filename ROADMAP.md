# IRONCLAD v1.0 delivery status

| Phase | Delivered | Evidence |
| --- | --- | --- |
| 1 | Typed agent messages, AST evidence, CLI, immutable replay | Unit and integration tests |
| 2 | Six-role workflow, guarded edits, Docker checks, bounded correction, flake detection | Passing real Docker repair in GitHub Actions |
| 3 | Authenticated API, persistent queue, live event streaming | API tests and real 500-client sustained benchmark |
| 4 | Seven workspaces, virtualized/paginated incidents, trace, diff rationale, replay, keyboard navigation | Production build, automated accessibility/interaction and contrast tests |
| 5 | Review gate, stale-code protection, idempotent draft PRs, signed/deduplicated webhooks | Unit/integration tests; real paid-provider activation described below |
| 6 | PostgreSQL/pgvector, BM25 fusion, Redis dispatch, fenced leases, telemetry, Compose, launchers | Live service tests, telemetry test, frontend/backend CI |

## External activation still required

The real hosted-model → Docker verification → actual draft PR acceptance workflow is implemented, but has **not been run with a paid model** because provider credentials are not configured in this environment. Configure the provider secret and model/pricing variables described in README.md, then run the opt-in `workflow_dispatch` acceptance job. No test result is fabricated for this step.

Automated accessibility tests and contrast checks are included. They are not a complete manual screen-reader/browser accessibility certification. Load results establish 500-client local transport behaviour for 30 seconds, not unlimited scale or a browser-rendering latency guarantee.

Phase branches preserve development milestones; `main` contains the current implementation and hardening fixes.
