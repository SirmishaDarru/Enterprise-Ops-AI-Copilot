# Stage plan and acceptance criteria

Source: supplied project brief (`Pasted text(3).txt`) and Stage 0 instruction (`Pasted markdown.md`). A stage is complete only after implementation and evidenced verification; checkboxes below indicate work done, not intent.

| Stage | Requirements mapped from brief | Acceptance gate |
| --- | --- | --- |
| 0 Design | Four capabilities, modular monolith, roles, data, queue, contracts, costs, exclusions, Windows prerequisites | Reviewable plan, architecture, README and truthful status. |
| 1 Foundation | API design, auth/RBAC, audit base, PostgreSQL models/migrations, React shell | Fresh setup; migrations, login, health/readiness, protected request and denied role tests pass. |
| 2 Operational foundation | Service/dependency models; synthetic logs/metrics; dashboard; thresholds/alerts; incident lifecycle, deduplication and searchable timeline; deployment-event fixtures | Seeded failure produces alert and one incident, visible telemetry and timeline through UI. |
| 3 Knowledge/RAG | Runbooks, service docs, postmortems and guides; parsing, chunking, embeddings, pgvector plus lexical search; operational Q&A, citations and document permissions | Relevant, ambiguous and restricted fixture queries return inspectable authorized sources; update/delete do not leak stale chunks. |
| 4 Investigation | Structured summaries, observations vs hypotheses, anomalies, historical incidents, dependency/deployment context, diagnostic recommendations; provider abstraction and cost tracking | Seeded case has valid source links; insufficient evidence, fabricated citation, timeout and malformed provider responses handled. |
| 5 Workflows | Explicit states; async jobs; retry, timeout, cancel, recovery and idempotency; allowlisted typed tools; approval, audit and execution budgets | Diagnostic run pauses and resumes with exact approval; crash/retry and duplicate delivery do not duplicate a simulated consequence. |
| 6 Evaluation/hardening | Labelled cases; retrieval, grounded claims, hypothesis/tool quality, latency and usage; injection, ACL and failure tests | Reproducible report identifies dataset and deterministic vs human checks; mock/live results separate; tests cover bypass and recovery. |
| 7 Observability/reproducibility | Traces, logs, metrics, OTel, Prometheus/Grafana, Docker Compose, CI, health, backup/restore | Lint/type/tests/build pass; instrumented journey visible when stack runs; unsupported setup paths marked pending. |
| 8 Integrated review | Three end-to-end demonstrations, security/accessibility/migration/reliability review | Evidence-backed investigation; crash-safe approved workflow; reproducible evaluation; gaps classified and material bugs fixed. |
| 9 Portfolio | README, diagrams, demo and troubleshooting, honest limits, resume/interview material | Every claim traceable to repository evidence; user can explain choices and run five-minute demo. |

The original 16-point checklist is covered explicitly: service/incident/alert models (1–2), APIs/dashboard (1–2), synthetic telemetry (2), thresholds (2), runbook ingestion (3), retrieval/citations (3), structured summaries (4), labelled comparison (6), workflow states (5), async execution (5), retries/timeouts/idempotency (5), approved tools (5), auth/RBAC/audit (1 and 5), integration/recovery tests (5–6), latency/error/token cost instrumentation (4 and 7), Docker/CI (7).

## Stage 0 status

- [x] Inspect available workspace and instructions; find and read original brief.
- [x] Record final capabilities, boundaries, roles, entities and API conventions.
- [x] Select PostgreSQL durable queue with separate worker and document tradeoffs.
- [x] Define retrieval, investigation schema, workflow states and acceptance gates.
- [ ] Verify the user's Docker Desktop PostgreSQL/pgvector setup locally. The user requested downloadable files instead of repository edits.

## Stage 1 implementation order

1. Inspect the provided repository and instructions; preserve existing changes. If none is provided, import this Stage 0 design into a new repository only when its destination is clear.
2. Verify WSL2 or selected alternative, PostgreSQL and pgvector prerequisites. Lock tested Python and Node dependencies; document exact versions and setup. A `.env.example` contains names and nonsecret local defaults only.
3. Create migration-managed foundation and modular backend, auth/RBAC and audit hook. Seed local demo identities; never ship known production credentials.
4. Build typed React authenticated shell and error/loading states.
5. Run migrations, API/UI builds and meaningful auth tests; record exact evidence in `docs/status.md`.

Stage 1 code now exists in the downloadable project. The Stage 1 acceptance gate remains pending a real PostgreSQL migration, seed, login, and protected request on the user's machine; see `status.md`.

## Stage 2 implementation status

- [x] Migration and models for aggregate metrics, logs, deployment markers, alert rules/events and incident timeline.
- [x] Fixed synthetic fixture and replay endpoint; active-incident and repeated-sample deduplication rules.
- [x] Scoped service/dashboard, metric/log, alert and incident APIs with search and cursor pagination.
- [x] Dashboard, metric chart, searchable logs, incident detail and timeline, threshold editor and status actions.
- [x] Source-level tests, offline PostgreSQL DDL generation, lint and frontend build.
- [ ] Execute migration, replay and opt-in integration test on a running Docker PostgreSQL instance; inspect the full UI demonstration.

## Stage 3 implementation status

- [x] Migration, bounded document extraction, versioned chunks and pgvector/lexical hybrid retrieval.
- [x] SQL permission checks and source inspector; synthetic relevant, ambiguous and restricted fixtures.
- [x] UI upload/replace/reindex/delete and deterministic mock embedding mode for tests.
- [x] Lint, unit tests and frontend build.
- [ ] Execute migration and opt-in ACL/stale-chunk test against user's Docker PostgreSQL; inspect fixture search in browser.

## Stage 4 implementation status

- [x] Bounded structured evidence collection, provider abstraction, deterministic mock and optional live adapter.
- [x] Citation-ID validation, observations vs hypotheses, failure codes, owner-scoped report history, usage and latency records.
- [x] Interactive report UI with citation inspection, unit failure tests, lint, offline migration and frontend build.
- [ ] Apply migration, run opt-in PostgreSQL tests and inspect seeded report in user's browser.
- [ ] Exercise any optional live provider with user-provided key; no live call is claimed here.

## Stage 5 implementation status

- [x] PostgreSQL durable queue, leases, retry/timeout/cancellation, explicit states and separate worker.
- [x] Typed diagnostic tools, exact plan approval by another account, unique transactional simulated effect and audit trail.
- [x] Workflow API/UI, unit state-machine tests and opt-in crash/retry PostgreSQL test.
- [x] Source lint, frontend build and offline migration DDL.
- [ ] Execute migration, opt-in integration test and two-account UI walkthrough on user's Docker PostgreSQL.

## Stage 6 implementation status

- [x] Labelled synthetic corpus, scoring formulas and separate offline, PostgreSQL/mock and optional live reports.
- [x] Automated citation/uncertainty, failure, injection attempt, approval-plan and ACL/stale-source checks.
- [x] Report sample, admin Evaluation UI, source tests, lint and frontend build.
- [ ] Run PostgreSQL evaluation and integration tests on user's Docker installation; inspect retrieval ranks.
- [ ] Human review of semantic support, diagnostic quality and optional live-model prompt-injection response.

## Stage 8 implementation status

- [x] Three-journey operator runner with redacted success report and explicit mock-provider preflight.
- [x] Existing seeded account password reset command, restricted to development and explicit flag.
- [x] Source review and accessibility state semantics; repeat source checks and frontend build.
- [ ] Run the journeys and PostgreSQL crash/retry evaluation on the user's Docker instance.
- [ ] Complete manual semantic citation review, keyboard/screen reader walkthrough, and backup restore drill.

## Stage 9 portfolio handoff

- [x] Portfolio README, architecture overview, timed five-minute demo, troubleshooting and interview notes.
- [x] Claim-to-evidence map with source paths and explicit limits.
- [ ] Record the user's own Docker, PostgreSQL, browser and manual review evidence before describing those gates as passed.

## Stage 10 observed local target

- [x] Separate live checkout HTTP target, traffic generator, collector, failure toggle, bounded ingestion cursor and alert/incident path.
- [x] Provenance labels distinguish observed local HTTP batches from Stage 2 synthetic fixture.
- [x] HTTP server test, source lint, frontend build and opt-in collector PostgreSQL test definition.
- [ ] Run the full chain, migration, database integration test and operator review on the user's Docker instance.
