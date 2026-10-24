# Architecture and decisions — Stage 0

## Scope and boundaries

Final scope follows the supplied Enterprise AI Operations Copilot brief: service and dependency health; synthetic logs/metrics, alerts, incidents and timelines; knowledge ingestion and permission-aware hybrid retrieval; cited, structured incident investigation and operational Q&A; durable diagnostic workflows, retries, approval and audit; evaluation, observability and reproducible setup.

Explicit exclusions for this portfolio implementation: production telemetry ingestion agents and vendor integrations, unrestricted shell/model execution, unattended real remediation, production SSO, public multi-tenant hosting, and calibrated probability claims. These exclusions do not remove the agreed simulated diagnostic and approval demonstrations. Recent deployment *events* are first-class fixture data, not a deployment system integration.

One FastAPI application owns domain modules `auth`, `telemetry`, `incidents`, `knowledge`, `investigation`, `workflows`, and `audit`. A separate worker imports domain services but cannot bypass their authorization, state-machine, or audit rules. React consumes versioned HTTP contracts. PostgreSQL owns relational state, full-text indexes, vectors, and durable jobs. All timestamps are UTC at storage/API boundaries; frontend displays local time.

## Roles and enforcement

| Role | Access |
| --- | --- |
| Viewer | Read permitted services, incidents, telemetry, and knowledge; request permitted search. |
| Responder | Viewer access plus create/update assigned incidents and request investigations and allowlisted diagnostic workflows. |
| Approver | Responder access plus approve/reject consequential proposed actions within an authorized service scope; cannot approve own proposal (separation of duties). |
| Admin | Manage users, service scopes, documents, thresholds, and tool policy; can approve only through the same binding and audit checks. |

Every request is authenticated; both role and service/document scope are checked in the service layer and again before retrieving evidence or executing a tool. Default deny. Seed users are local-only. Session/token design and library versions are finalized in Stage 1. The worker uses a scoped service identity and rechecks the requesting user's authorization where the operation depends on it. Historical audit rows preserve actor and authorization decision.

## Data model (planned)

| Entity | Key relationships and purpose |
| --- | --- |
| `users`, `service_memberships` | Identity, role, and permitted service scope. |
| `services`, `service_dependencies` | Directed dependency graph and ownership. |
| `log_events`, `metric_samples`, `deployment_events` | Time-bounded, source-addressable operational evidence; synthetic fixture provenance. |
| `alert_rules`, `alert_events`, `incidents`, `incident_events` | Thresholds, deduplicated alert occurrence, lifecycle, append-only timeline. |
| `documents`, `document_grants`, `document_chunks` | Source version, ACL, stable chunk identity, text search vector, embedding and model/version metadata. |
| `investigations`, `evidence_refs`, `model_calls` | Validated output, source snapshot references, provider/model/usage/latency/error. |
| `workflows`, `workflow_steps`, `jobs`, `action_proposals`, `approvals`, `tool_invocations` | Persisted orchestration, leases, exact action binding, effects, and results. |
| `audit_events` | Append-only actor/action/target/decision/correlation/time with secret redaction. |

Use UUID identifiers, foreign keys, useful uniqueness constraints, and migration-managed schemas. Source refs are typed (`log`, `metric_window`, `deployment`, `incident`, `document_chunk`, `tool_result`) and resolve through an authorized API. Metric-window references include immutable query bounds and fixture/snapshot identity; a citation must not silently change as new samples arrive. Document chunks belong to one immutable document version; updates replace the active searchable version transactionally and deletion removes or deactivates all chunks. The Stage 2 fixture is finite; retention for larger or live telemetry is future work.

Stage 2 uses one-minute aggregate `metric_samples` with requests, errors and p95 latency, alongside `log_events` and `deployment_events`. A deterministic UUID namespace and fixed UTC fixture time make replay idempotent. `alert_events` are unique on `(rule_id, sample_id)`, and a PostgreSQL partial unique index allows only one open/investigating incident for a service/rule pair. Evaluation locks the rule row before checking for an existing alert, serializing concurrent evaluations of the same rule. A resolved incident remains historical; a *new* breaching sample can open a new incident. This is synthetic evidence, not a live telemetry collector. The first threshold is a per-sample error percentage, with integer percentage comparison; additional windowing strategies belong to future work.

## API and frontend contract

- `/api/v1/...`, JSON with UTC ISO-8601 timestamps, UUID IDs, typed Pydantic request/response models, generated OpenAPI. Frontend uses generated or checked typed contracts rather than duplicating shapes silently.
- Pagination uses `limit` plus an opaque cursor for logs, incidents and audit streams; stable sort by `(occurred_at, id)`; filter by service, severity and time bounds where relevant. Document and service lists can use the same convention.
- Errors: `{ "error": { "code": "STABLE_CODE", "message": "safe description", "details": [] }, "request_id": "..." }`, with consistent 400/401/403/404/409/422/429/503 semantics. No stack traces or hidden resource details in responses.
- Proposed resources: `/auth`, `/services`, `/telemetry/logs`, `/telemetry/metrics`, `/alerts`, `/incidents`, `/documents`, `/knowledge/search`, `/investigations`, `/workflows`, `/approvals`, `/audit`. Creation of long-running investigations/workflows returns `202` with a resource ID and status URL; UI polls with bounded intervals. Mutation endpoints accept an idempotency key where duplicate requests can occur.
- Dashboard, incident detail, document/search inspector and workflow review UI display loading, empty, error and forbidden states. Approval UI shows exact tool, arguments, incident, proposer and expiry before submission.

## Knowledge and investigation

Stage 3 supports UTF-8 `.txt` and `.md` first, plus text-based `.pdf` if parsing tests and size limits succeed. No OCR or arbitrary URLs. Validate extension, media type, bytes, page/character limits, and extracted text; do not execute embedded content. Normalize text, chunk by headings/paragraphs with overlap, assign deterministic `(document_id, version, chunk_ordinal)` IDs, hash content, and cache embeddings for unchanged content with the same embedding model/version. Bound file size, chunks per file, batch size and embedding retries.

Store vectors in pgvector and lexical terms in PostgreSQL full-text search. Pre-filter authorized documents and service scope in SQL for both candidates, merge bounded ranked lists, then rerank or use reciprocal rank fusion; check ACL again when rendering citations. Search returns authorized snippets and stable source refs. Model input receives only bounded, authorized evidence, each item with a source ID; treat all text as untrusted instructions. Historical incident search uses authorized, labelled incident records and relevant text, with a simple lexical baseline before optional incident embeddings.

Investigation output schema: `summary`, `observations[{claim,evidence_refs}]`, `hypotheses[{claim,evidence_refs,reasoning,missing_evidence}]`, `uncertainty`, `recommended_steps[{description,tool_key?,arguments?}]`, `source_refs`, `model_metadata`. Validate all refs against the retrieved evidence set, require evidence on substantive claims, allow an empty hypothesis list, and reject fabricated IDs or malformed output. Correlation is labelled as such; no numerical confidence field. An operational Q&A answer uses the same authorized retrieval and citation checks. Provider interface supports `mock` and one configurable `live` adapter; token/latency/cost records use configurable pricing assumptions, with unknown cost when pricing is unavailable. Timeouts and rate limits return explicit recoverable states.

## Durable jobs and workflow state

Use a **PostgreSQL job table and dedicated polling worker**, avoiding a Redis service. PostgreSQL documents `FOR UPDATE SKIP LOCKED` for queue-like consumers. In one transaction, claim a due job with `SKIP LOCKED`, set owner, lease expiry and attempt, and commit. Heartbeat/extend the lease during bounded execution; a sweeper requeues expired claims. A delayed `run_after` plus capped exponential backoff handles retryable failures; terminal failure records the cause. Index `(status, run_after)` and monitor oldest due age and queue depth. PostgreSQL availability is a prerequisite; polling latency is acceptable for this project. This is **at-least-once delivery**, not exactly-once execution. Database transactions, unique effect keys, guarded transitions and tool-specific idempotency protect effects. External side effects require an idempotent target or reconciliation before any real integration is claimed.

Workflow states: `queued → running → waiting_for_approval → queued → running → completed`, with `running → queued` for retry/recovery, `queued/running/waiting_for_approval → cancelled`, and `queued/running/waiting_for_approval → failed` for exhaustion/rejection/expiry. A running workflow may finish without approval for read-only tools. Terminal states have no outbound transitions. Cancellation marks intent transactionally; worker checks before each step and before recording effects. Steps have their own attempts and durable outputs; the workflow is not completed until results commit.

Consequential actions use a server-side allowlist of typed tools. Approval binds a canonical hash of `(workflow_id, incident_id, tool_key, tool_version, normalized_arguments, proposer_id)` plus approver, expiry and one-use state. Any proposal edit creates a new hash and invalidates old approval. Transactional compare-and-set consumes approval before an effect; replays return the stored result. Only clearly labelled simulation executes in the agreed scope. Tool and workflow budgets bound calls, duration, attempts and results. Audit every proposal, decision, transition and invocation.

## Tests, observability, and risks

Unit tests cover rules and schema validation; PostgreSQL integration tests cover migration, SQL ACL pre-filter, alert deduplication, concurrent claims, lease expiry, stale approvals and duplicate effects; API tests cover unauthorized/forbidden access; UI tests cover critical states; deterministic fixture demos cover the three final journeys. Mock LLM tests are separate from opt-in live checks. Stage 6 reports retrieval recall/precision at k and citation validity with dataset size and method; human review assesses hypothesis quality. No fabricated scores.

Instrument request/trace IDs across API, jobs, retrieval, provider and tools. Redact secrets and sensitive document contents in logs. Stage 7 ships Prometheus scrape config, useful Grafana dashboards, Compose, CI, startup/backup guidance and verifies only the setup paths actually run.

Risks: local PostgreSQL/pgvector setup (Stage 1 now defaults to a pinned pgvector Docker image; verify Docker Desktop and the extension on the user's machine); PostgreSQL queue contention and lease design (concurrency/crash tests); prompt injection and ACL leakage (SQL pre-filter plus output validation); misleading incident causality (label correlation and insufficient evidence); external action replay (simulated first, no exactly-once claim); model cost drift (limits, mock tests, explicit pricing config). Provider and dependency versions will be locked and checked against official docs at their implementation stages.

## Stage 7 local deployment

`db` remains the default Compose service so `docker compose up -d db` continues to work. The `full` profile runs migration, API, worker, frontend and Jaeger. The `observability` profile adds Prometheus and Grafana. API metrics are scraped inside the Docker network at `api:8000/metrics`; worker metrics at `worker:9101/metrics`. Both processes send OTLP/HTTP spans to Jaeger when configured. No distributed context is persisted on workflow records; API and worker traces are separate, correlated through workflow IDs and response request IDs. Local Jaeger trace storage is transient. The dashboard is a development aid, not an alerting or production retention system.
