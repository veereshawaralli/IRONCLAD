# Phase 5 · Review, draft PRs and signed CI webhooks

The reviewer must confirm that the diff and checks were inspected. Only a run with a passing latest verification and reporter output can be approved. Simulation runs are denied. The GitHub adapter uses a single environment-scoped repository, checks file SHA-256 baselines before edits, creates a dedicated repair branch and draft PR, and never merges. Existing PRs are reused. Mutation calls are not blindly retried after ambiguous outcomes; GET calls have bounded retries and rate-limit/circuit-breaker handling.

Configure `IRONCLAD_GITHUB_REPO=owner/repo` and `IRONCLAD_GITHUB_TOKEN` with repository contents and pull-request write access. Tokens are server-only. The adapter never emits co-author trailers or assistant attribution.

Webhook endpoint: `/api/webhooks/github`. Configure a high-entropy `IRONCLAD_WEBHOOK_SECRET`. HMAC-SHA256 signatures, repository scope and delivery deduplication are enforced. Completed failed check runs queue hosted diagnosis. Logs are bounded and still need secret hygiene at the source.

The configured local repository must correspond to the intended revision. Webhook ingestion records the CI head SHA but does not automatically check out arbitrary commits. PR publication rejects changed remote files. No real target-repository PR was opened during testing; mocked end-to-end tests cover review and idempotent publication.
