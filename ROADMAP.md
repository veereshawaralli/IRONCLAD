# IRONCLAD delivery roadmap

| Branch | Delivery | Status |
| --- | --- | --- |
| phase-1 | Typed events, CLI diagnosis, guarded proposals | Implemented and tested |
| phase-2 | Supervisor, Docker verifier, bounded reflection | Implemented; Docker runtime validation pending |
| phase-3 | API, durable queue, streaming dashboard | Implemented and tested |
| phase-4 | Incident inspection, replay, diff rationale | Implemented; visual/accessibility audit pending |
| phase-5 | Review gate, draft PR adapter, signed webhooks | Implemented; real target integration validation pending |
| phase-6 | Compose deployment, metrics, CI, documentation, fan-out test | Implemented with measured limits documented |

## Remaining original-spec work

- Distributed worker leases and production Redis dispatch.
- Broader provider retry/circuit-breaker policies beyond the bounded current adapters.
- Full WCAG AA testing and paginated history beyond the current 1,000-record feed.
- Actual Docker and hosted-model-to-GitHub end-to-end acceptance run.
- Sustained 500-dashboard traffic and under-200ms live-event latency verification.

The local application is usable; these original production requirements remain explicitly open. Phase branches are milestones, not claims that every broad acceptance criterion is complete.

Phase 6 also includes PostgreSQL storage, optional pgvector/BM25 RRF retrieval, TanStack Virtual, Redis mirroring and OTLP spans. External services are covered by service-backed CI jobs; they were not available locally.
