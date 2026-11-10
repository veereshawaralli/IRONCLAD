# Phase 2 · Verification and repair loop

Added an explicit bounded fleet graph with six agent roles, exact evidence scope, repeated-patch cycle detection, a three-attempt ceiling and terminal escalation. Model reservations are committed to SQLite before requests, preventing a crash from silently restoring the same run's spend allowance.

DockerSandbox copies only bounded permitted Python source into a disposable snapshot. Each baseline/patched check uses a fresh non-root container with no network, read-only root filesystem, CPU/memory/PID limits, no capabilities and bounded time. It compares pytest case failures and requires passing lint, mypy and Bandit checks. Docker is mandatory; no host execution fallback exists.

Build the image: `docker build -f Dockerfile.sandbox -t ironclad-sandbox:local .`

Validated: 24 tests, strict mypy, Ruff. Workflow tests use an injected fake verifier. Docker is unavailable in the build workspace, so actual container execution is not verified here. The initial supported target is a Python repository whose tests need only the sandbox's installed tools. Arbitrary third-party dependencies require a curated image; no dependency installation from an untrusted target occurs.
