# Claim-to-evidence map

Use these paths to check a portfolio or interview statement before making it. Paths are relative to the ZIP root. "Source" means implementation or a test exists; it does **not** mean the full Docker journey passed in this environment.

| Claim you can substantiate | Implementation | Check / limit |
| --- | --- | --- |
| Local JWT login, role checks and service memberships | `backend/app/auth/`, `backend/app/core/access.py`, `backend/alembic/versions/0001_foundation.py` | `backend/tests/test_api.py`, `test_security.py`; seeded accounts remain local demo accounts. |
| Synthetic telemetry creates threshold alerts, one active incident and timeline | `backend/app/telemetry/demo.py`, `backend/app/incidents/service.py`, `0002_operational_data.py` | `backend/tests/test_stage2.py`, `test_stage2_postgres.py`; no production collector. |
| Permissioned hybrid retrieval and inspectable chunk sources | `backend/app/knowledge/routes.py`, `service.py`, `0003_knowledge.py` | `backend/tests/test_stage3.py`, `test_stage3_postgres.py`; small fixture, no OCR. |
| Structured investigation validates citation IDs and read-only recommendations | `backend/app/investigation/`, `0004_investigations.py` | `backend/tests/test_stage4.py`, `test_stage4_postgres.py`; ID validation does not establish semantic support. |
| Worker handles leases, retries, exact approval and one simulated effect | `backend/app/workflows/`, `0005_workflows.py` | `backend/tests/test_stage5.py`, `test_stage5_postgres.py`; opt-in DB test injects precommit crash. No real remediation. |
| Deterministic evaluation and labelled PostgreSQL retrieval | `backend/app/evaluation/`, `docs/evaluation-method.md` | `backend/tests/test_stage6.py`, `test_stage6_postgres.py`, sample report; offline mode does not measure retrieval. |
| Local metrics, traces and reproducible container definitions | `backend/app/observability/`, `compose.yaml`, `docker/`, `.github/workflows/checks.yml` | `backend/tests/test_stage7.py`; actual stack/trace/CI execution still pending here. |
| Three-journey operator review and explicit password reset | `backend/app/review/run.py`, `backend/app/seed.py` | `backend/tests/test_stage8_review.py`, `test_stage8_seed.py`; live API runner still pending here. |

Keep numbers precise: Stage 10 source checks passed 35 tests and skipped six PostgreSQL integration tests in this environment. The new HTTP server test also passed. The offline sample is 8/8 deterministic checks and is **not** a real-world quality score. Do not describe the project as deployed or production ready without new evidence.

## Stage 10 additions

| Claim | Implementation | Check / limit |
| --- | --- | --- |
| Observed local checkout requests lead to stored metrics, logs and alerts | `demo_service/server.py`, `traffic.py`, `backend/app/telemetry/live.py`, `0006_live_demo_cursor.py` | `demo_service/test_server.py`, `backend/tests/test_stage10.py`, `test_stage10_postgres.py` (DB test pending here). The controlled target is local, not production. |
| Admin controls failure and a live runbook can be cited | `backend/app/telemetry/live_routes.py`, `backend/app/knowledge/routes.py`, `frontend/src/App.tsx` | Role test in `test_stage10.py`; API/Compose journey still pending here. |
