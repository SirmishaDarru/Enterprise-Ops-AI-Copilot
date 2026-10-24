# Stage 8 integrated review

This is a review procedure and a list of source findings, **not** a claim that the Docker journeys have run here. Use a copied Stage 7 folder and retain `backend/.env` and the database volume.

## Three local demonstrations

1. **Cited investigation:** replay the finite synthetic incident, load the demo runbooks, generate one report using the mock provider, check citation IDs and uncertainty, then retrieve each cited runbook source with the responder account.
2. **Approval and replay protection:** queue diagnostics as a responder, wait for the worker's approval request, deny viewer access, approve with a different account and check one simulated completion. Queue an approver-owned proposal and confirm that same approver cannot approve it. The existing opt-in PostgreSQL test injects a failure before commit and checks rollback, retry, stale leases and duplicate effect suppression; the API runner does not crash the live worker.
3. **Evaluation:** run eight deterministic offline checks via the admin API and record the dataset digest. Run the separate PostgreSQL labelled retrieval evaluation from its CLI; it creates temporary rows and rolls them back. Inspect citations and hypotheses manually before claiming semantic quality.

The script writes a compact JSON report with IDs, counts and statuses, without passwords or document passages. It changes only local synthetic demo state; re-running it creates fresh investigation/workflow history. Require `INVESTIGATION_PROVIDER=mock` in the running API and matching `backend/.env`. If runbooks were indexed with another embedding mode, reindex them after changing mode.

## Review findings

| Area | Evidence and action | State |
| --- | --- | --- |
| Identity | `app.seed` previously left an existing demo password untouched. Explicit `--reset-password` now changes it in development only; no reset happens on normal seed. | Fixed; source tests pass. |
| Approval | A responder lacks approver role, and a requester with approver role is rejected by the `SELF_APPROVAL` check. Worker validates scope, plan hash, approver identity and state again before recording a simulated effect. | Source reviewed; runtime journey pending. |
| Retrieval access | Search candidates and final source fetch apply SQL grants and service scope; prior PostgreSQL integration tests include restricted and stale source cases. | Source reviewed; PostgreSQL run pending. |
| Accessibility | Inputs have visible labels, error/status messages use live roles, chart has a text label. Navigation now exposes current page, and selected service/incident controls expose pressed state. | Source reviewed and TypeScript build passed; keyboard/screen reader walkthrough pending. |
| Migration | Stage 8 adds no schema revision. The Compose migration job runs Alembic; CI defines a pgvector PostgreSQL service and migration before DB tests. | Definition reviewed; Compose/CI execution pending. |
| Reliability | Workflow unique effect and exact approval checks have an injected-crash integration test. Local backup script uses `pg_dump` and restore targets a fresh database. | Source reviewed; worker crash, backup restore and database integration pending. |

## Manual acceptance checklist

- [ ] Run Stage 8 API script and inspect its JSON report on the user's Docker stack.
- [ ] Run `TEST_DATABASE_URL=... pytest -q` and the PostgreSQL evaluation against a migrated local database.
- [ ] Open Grafana and Jaeger after the API journey; verify API/worker metric samples and trace spans.
- [ ] Restore a backup into a *new* database and confirm Alembic revision and expected row counts.
- [ ] Keyboard navigate login, incident, source and approval screens; verify labels and visible focus.
- [ ] Read each investigation claim against its cited evidence; mark unsupported claims and uncertain causal wording explicitly.

Stage 8 is source-ready only until these checks are actually observed. No Docker test or browser walkthrough was run in this workspace.
