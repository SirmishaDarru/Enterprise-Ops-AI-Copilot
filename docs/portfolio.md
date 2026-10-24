# Portfolio and interview notes

## Short description

Built a local AI operations copilot for synthetic service incidents: threshold alerts and incident timelines, permissioned hybrid runbook retrieval, cited structured investigations, and an approval-gated PostgreSQL worker that records a simulated action. Added deterministic evaluation, local observability and a repeatable Docker setup. Full Docker and PostgreSQL acceptance is pending in the delivered workspace; verify it on your own machine before presenting it as completed.

## Resume bullet options

Select two or three that match what you have personally run and can explain:

- Built a FastAPI/React operations dashboard over PostgreSQL with synthetic telemetry, threshold-based alerting, incident deduplication and searchable timelines.
- Implemented role- and service-scoped runbook retrieval using pgvector and PostgreSQL full-text search, with inspectable source IDs and stale-source tests.
- Designed a durable PostgreSQL workflow worker with leases, `SKIP LOCKED`, bounded retries, exact approval hashes and a transactionally unique **simulated** effect.
- Added structured investigation validation for citation IDs, uncertainty and read-only recommendations, plus deterministic mock tests and optional explicit live provider mode.
- Created a labelled evaluation fixture, Prometheus metrics, local OpenTelemetry traces, Docker Compose definitions and CI checks; documented which integration gates still require Docker execution.

These describe implementation, not unverified business impact. Do **not** claim production deployment, a real incident reduction percentage, model accuracy, real remediation or full end-to-end verification until you have evidence.

## Explain the design in an interview

1. **Data and failure mode.** The Stage 2 fixture is finite and repeatable. Alert uniqueness is per rule/sample; a partial index keeps one active incident per service/rule. A resolved incident remains history.
2. **Authorization boundaries.** The API checks identity and service membership. SQL restricts document candidates and final source reads. Historical investigation snapshots are denied if their source is no longer authorized.
3. **Retrieval and citations.** Vector and lexical candidates are merged with reciprocal rank fusion. Structured report validation rejects fabricated IDs and unsafe recommendation verbs, but cannot prove semantic entailment.
4. **Queue semantics.** One worker claim takes a row lock and lease. A crash can cause redelivery. Transactional state/effect commits, exact approval checks and a unique action key make the local simulated effect idempotent.
5. **Evaluation.** Offline checks cover structure, failure handling and injection examples; PostgreSQL mode measures a labelled tiny corpus, access boundaries and rollback. A human reviews causal wording and citation support.
6. **Limits and extension.** Explain how production SSO, ingestion, external-action idempotency/reconciliation, richer evaluation, persistent traces, monitoring and hardening would change the system.

## Evidence to bring to a demo

- A screenshot or live walkthrough of one cited investigation and its source passage.
- One workflow's approval plan, distinct approver, completed simulated effect and audit timeline.
- The JSON from `app.review.run` plus the separate `evaluation-postgres` report, if they passed on your machine.
- `ruff`, full `pytest` with migrated `TEST_DATABASE_URL`, frontend build, backup restore and any CI run logs. Do not imply a skipped check passed.

Use `docs/evidence-map.md` to connect each talking point to code and tests. Use `docs/status.md` to keep current claims honest after running additional checks.

## Stage 10 observed-service improvement

The project now includes a separate **local** HTTP checkout target and a traffic generator. The collector stores real handled-request status and duration data, then triggers a threshold alert. This closes the earlier gap where checkout incidents came only from a fixed fixture. The failure is still deliberately injected, and the target is not a real payment or production system. A defensible resume phrase after you run the Docker chain is: “Integrated a controlled checkout HTTP service with request-driven metrics/log ingestion and alert-to-incident flow; kept remediation simulated and approval gated.” Keep the Docker run report and a cited live incident as evidence; do not claim this end-to-end check passed before actually running it.
