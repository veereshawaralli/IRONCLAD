# Acceptance matrix

| Requirement | Status | Verification |
| --- | --- | --- |
| Failure → diagnosis → scoped patch → isolated checks → report | Passed | Real Docker fixture smoke test in Actions |
| Bounded self-correction and cycle detection | Passed | Hosted-adapter workflow and failure-path unit tests |
| Guardrails and durable budget reservations | Passed | Scope, path, syntax, cost, non-finite-value and restart tests |
| Concurrent workers and crash recovery | Passed | Fenced lease and heartbeat tests, including PostgreSQL |
| Typed durable Redis messages and queue dispatch | Passed | Live Redis tests and SQL recovery path |
| Reconnectable, ordered event stream | Passed | Replay and shared hub tests; 75,000-event load run |
| 500 clients, under-200ms delivery p95 | Passed within measured scope | 30 seconds, 59.79ms p95 on Actions; no browser rendering measurement |
| PostgreSQL / pgvector / BM25 retrieval | Passed | Live service tests plus ranking and citation tests |
| Review confirmation, stale-code rejection, draft-only PR publisher | Passed for tested adapters | Integration tests and opt-in live workflow |
| Real paid model → actual GitHub draft PR | Not run | Provider credentials/model/prices absent; requires configured external service |
| UI semantics, keyboard interactions and theme contrast | Passed automated checks | React/axe tests plus stylesheet contrast tests |
| Full manual WCAG/browser certification | Not claimed | Automated checks do not establish this |
| Windows/local setup | Launcher implemented | `py -3.12 start.py`; Windows OS runtime not available for local validation |
