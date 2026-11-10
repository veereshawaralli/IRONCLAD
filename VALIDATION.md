# Delivery validation · 2026-11-10

Python 3.12.14. Installed editable package with development dependencies.

- `python -m pytest -q --cov=ironclad --cov-report=term-missing`: **20 passed**.
- Overall statement coverage: **81%**. Engine: **96%**. Repository retrieval/guardrails: **90%**.
- Integration fixture: generated unified patch applied with `git apply` to a temporary repository; both fixture tests passed.
- `python -m ruff check ironclad tests`: passed.
- `python -m mypy ironclad`: strict typecheck passed across 8 source files.
- CLI demo and help executed successfully.
- Hosted model tests use mocked HTTP responses, including malformed JSON then retry. No paid API or GitHub call was made.
- Redis relay tested with an in-memory fake, not a live Redis server.
- Test environment emitted an external AnyIO plugin pytest-deprecation warning; no project test failures.

No claims of browser QA, Docker sandbox verification, PR integration, WebSocket latency, or load testing apply to this first phase.
