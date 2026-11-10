# Validation · 2026-11-10

- Python 3.12; Next.js 15.5.29 / React 19; TypeScript strict.
- 37 Python tests passed, 2 service-backed tests skipped locally: guards, model JSON retry, immutable history, durable cost, bounded repair, API auth, settings, WebSocket replay, webhook signature/deduplication, review and mocked GitHub publication.
- Ruff checks and strict mypy pass across 17 Python application modules.
- Production Next.js static export compiled successfully; TypeScript validation passed.
- Overall Python statement coverage: 76%. Engine 96%, Fleet 84%, repository retrieval/guards 90%, API 88%. Docker execution wrapper coverage is 28%; actual container execution is not tested in this environment.
- The fixture integration test applies a generated diff to a temporary repository and runs its actual tests successfully.
- 500 local WebSocket replay clients succeeded, eight ordered events each, zero failures. Connection-plus-replay p95: 569.46ms; wall time: 1.19 seconds. See docs/load-test.json. This does not establish sustained load or under-200ms live-event latency.
- Hosted model and GitHub publisher integration use mocks. No paid provider calls or real repair PRs were made during development.
- Browser preview access was blocked by the execution gateway. No visual QA or WCAG certification is claimed.
- Docker is unavailable; Compose/sandbox runtime validation must be completed on a Docker-capable host.
- External AnyIO/Starlette test adapters emit deprecation warnings; tests pass.

Unimplemented original-spec items are listed in ROADMAP.md. The repository intentionally does not present the local v1 as fully production-certified.
