# Enterprise AI Operations Copilot · 

This release adds a **real local checkout HTTP service** and steady traffic to the earlier portfolio project. Its normal requests return 200; an admin can trigger a controlled 503 failure. A separate collector observes actual responses and durations, persists metrics and failure logs, and creates an alert and incident. The existing copilot can retrieve a live-service runbook, generate a cited investigation and run an approval-gated **simulated** workflow. This remains a local demo, not production monitoring or real remediation. This ZIP contains files, not a repository.

## Commands to run the project

From the folder containing `compose.yaml`:

```bash
docker compose --profile full --profile observability up -d --build
docker compose --profile full --profile observability ps
docker compose --profile full exec -T api alembic current
```

Expect revision `0006_live_demo_cursor`. The new `checkout-demo`, `checkout-traffic`, and `checkout-collector` services should be running; `checkout-demo` should be healthy. If you use a new extraction folder instead, the Compose project name and database volume may differ. Check `docker compose ls` and reuse the original project name with `docker compose -p OLD_PROJECT_NAME ...` for every command. Never use `docker compose down -v` when keeping data.

## Show the real HTTP chain

1. Open <http://localhost:8080/checkout-demo/checkout>. You should receive a real checkout HTTP 200 response. This proxy path reaches only the public checkout action; internal control stays inside Compose.
2. Open <http://localhost:8080>, sign in as `admin@local.example`, and on **Overview** click **Load live runbook**.
3. Select the **live-checkout-demo** card. Its recent samples are labelled **Observed local HTTP demo**. Click **Trigger checkout failure**.
4. Reopen the checkout URL: it should now return HTTP 503. Wait about 10 seconds and click **Refresh** in the app. The chart, error log and new incident should reflect observed requests.
5. Click **Restore checkout**. New requests return 200. As a responder, inspect the incident and generate a cited investigation; its runbook source is tied to the live demo service. Approval remains simulated.

If **Live checkout service** says unavailable, check `docker compose --profile full logs --tail=80 checkout-demo checkout-traffic checkout-collector api`. The new migration must finish before collector ingestion. For a no-cost demo, keep `INVESTIGATION_PROVIDER=mock`; use `EMBEDDING_MODE=mock` for deterministic runbook indexing or retain your existing indexed model mode. See [`docs/live-demo.md`](docs/live-demo.md) for the architecture, operator test command and limits.

## Verify and explain

From `backend` in Git Bash, run `py -3.12 -m uv sync --frozen --extra dev`, then `py -3.12 -m uv run --frozen python -m app.review.live_run --base-url http://127.0.0.1:8080 --output ../review-live-stage10.json`. It asks for the seeded password, checks the observed batch, alert and cited mock investigation, and clears the failure even if a check fails. The prior three-journey review and deterministic evaluation remain available. Read [`docs/status.md`](docs/status.md) before claiming end-to-end acceptance. For an interview, use the updated [`docs/demo.md`](docs/demo.md) and [`docs/portfolio.md`](docs/portfolio.md).

This target has an in-memory event buffer and fixed traffic. The collector records an explicit gap if it falls behind. A controlled pool-exhaustion message is **not** evidence of a real database outage. No production telemetry, real checkout transactions or external remediation is claimed.
