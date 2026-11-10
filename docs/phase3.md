# Phase 3 · API and live dashboard foundation

FastAPI endpoints provide installation-token sign-in, HttpOnly SameSite cookies, intent checks on mutations, a persistent queue, single worker, health, guardrails, incidents, citations, and reconnectable WebSocket event streams. The server fixes the repository from environment configuration rather than allowing arbitrary browser-provided filesystem paths.

Next.js 15 / React 19 / strict TypeScript static output is served by FastAPI for same-origin cookies and WebSockets. No simulated data is presented as real execution. The explicit demo creates labelled synthetic replay events, excluded from publication.

`IRONCLAD_ADMIN_TOKEN=<24+ random characters> python -m uvicorn ironclad.api:create_app --factory --host 127.0.0.1 --port 8000`

In a second terminal: `python -m ironclad.worker`. Build the frontend first with `cd web && npm ci && npm run build`.

SQLite WAL and the event log remain the local system of record. Redis/PostgreSQL deployment migration and distributed worker leases are not claimed implemented. One worker per installation is supported.
