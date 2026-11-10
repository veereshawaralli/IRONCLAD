# Release validation · 2026-11-10

## Verified

- Python 3.12; Next.js 15.5.29 / React 19; strict TypeScript.
- **57 local Python tests pass; 3 service-backed tests are skipped locally and run on GitHub.** Six frontend interaction/accessibility/contrast tests pass.
- Python unit/API/workflow tests cover immutable history, fenced leases, concurrent claims and approvals, webhook deduplication, cost limits, provider backoff, redaction, session expiry/revocation, payload limits, replay, correction, draft-only publication and stale-file rejection.
- Ruff and strict mypy pass. Core engine/fleet/repository coverage exceeds the 80% CI floor (approximately 91%).
- Automated React/axe checks cover login, overview, settings, knowledge, incident, replay, PR review and dialogs. Keyboard focus/Escape and selected small-text contrast checks are included. Colour contrast is disabled in axe's JSDOM run and checked separately against the actual stylesheet.
- Next.js production build and strict TypeScript pass.
- Actual PostgreSQL persistence/budget/lease, pgvector index/search and Redis Streams tests pass on GitHub runners.
- Actual restricted Docker smoke test reproduces `test_empty`, applies the guarded fixture fix, then passes pytest, Ruff, mypy and Bandit without regressions. Baseline test failures are checked for instability before accepting a patch.
- 500 concurrent clients received **75,000 live events** over 30 seconds with zero gaps/failures. Local p95: **50.10ms**; GitHub runner p95: **59.79ms**. This measures persistence → WebSocket delivery, excluding browser rendering. See `docs/live-load-test.json` and CI logs.
- OpenTelemetry span unit test checks run trace identity and step duration.
- No co-author trailers or assistant attribution are generated.

## Provenance

The acceptance workflow for commit `9a8756f2154209297caeebb36c90ecc22c62ac5d` passed backend, frontend and live service/Docker/load jobs:

https://github.com/veereshawaralli/IRONCLAD/actions/runs/42791712613

Later release fixes must also pass the current workflow; this recorded link is specific to the commit above, not a claim about an untested commit.

## Limits

The opt-in paid-model-to-real-PR test remains blocked by missing provider credentials/model/pricing configuration. Mocked model and publication tests are clearly identified. No paid-model run, real repair PR, full manual WCAG certification, unlimited scaling, or general-purpose secure execution guarantee is claimed.

The local worker image supports Python repositories with dependencies available in its curated image. Broader targets need an explicitly curated verifier image. PostgreSQL/Redis/Docker are tested in GitHub Actions because the development workspace lacks these servers.

External AnyIO/Starlette adapters emit deprecation warnings during local tests; these are not test failures.
