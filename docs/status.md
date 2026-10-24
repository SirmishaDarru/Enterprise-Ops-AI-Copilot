# Project status

Updated: 2026-10-23. Current stage: **Stage 10 observed local service source implemented; Docker chain pending**.

## Implemented

- Separate checkout HTTP server, steady request generator, internal bounded event buffer and a controlled 200/503 failure mode.
- Collector aggregates actual handled requests, persists metric samples and failed-request logs, evaluates an alert and advances an instance-aware cursor in one transaction. A gap is logged if the ring buffer overruns.
- Admin-only failure control, separate live runbook route, incident/dashboard provenance labels and a proxied checkout URL that does not expose internal control.
- `0006_live_demo_cursor` migration, Prometheus scrape target, Compose services, optional observed-chain review CLI and tests.

## Checked here

- Checkout server HTTP unit test: healthy request, controlled 503, event sequence, Prometheus counter and restoration passed.
- Ruff: passed. Backend pytest: **35 passed, 6 skipped** without migrated PostgreSQL. Frontend production build: passed. Local YAML/JSON/config checks: passed.
- Stage 6 offline sample remains 8/8 deterministic structural checks, not a real-world model score.

## Pending on the user's Docker stack

- Apply `0006_live_demo_cursor`, build/start all containers, run the observed-chain review and inspect real metrics, logs, alert, incident and cited investigation in browser.
- Run all six opt-in PostgreSQL tests (including Stage 10 collector transaction/idempotence), PostgreSQL retrieval evaluation and backup/restore drill.
- Inspect tracing and dashboards, keyboard/screen reader behavior and semantic citation support. No production readiness or live external remediation claim.
