# Five-minute Stage 10 demo

Before the timer, start the full Compose stack from `README.md`, confirm `checkout-demo` is healthy and traffic/collector are running, keep the mock investigation provider, seed the four local accounts, and click **Load live runbook** as admin. Check the checkout URL returns HTTP 200 while failure mode is OFF. You can rehearse with `app.review.live_run`; use a fresh output filename each run. Keep passwords private.

| Time | Action | What to explain |
| --- | --- | --- |
| 0:00–0:45 | Open `http://localhost:8080/checkout-demo/checkout` and get HTTP 200. Show the `live-checkout-demo` card. | A separate service is answering real local HTTP traffic; the copilot's collector stores observed batches. This is controlled demo traffic, not production. |
| 0:45–1:35 | Click **Trigger checkout failure**. Reopen the checkout URL for HTTP 503. Wait roughly 10 seconds, click **Refresh**, show error chart and logs. | The failure is deliberately injected. The ongoing traffic and collector produced the measurements, rather than a fixed database fixture. |
| 1:35–2:15 | Open **Incidents**, select the live checkout incident and show its alert and timeline. | Thresholded errors attach to one active incident. The recorded pool-exhaustion message is designed for this demo; it does not prove a real pool problem. |
| 2:15–3:00 | Sign in as responder, open **Investigations**, generate a mock report and inspect the live runbook citation. | The report separates observations from hypotheses and checks citation IDs. Human review is still required for semantic support. |
| 3:00–4:00 | In **Workflows**, queue diagnostics. Sign in as approver, inspect the exact plan and approve. | The worker rechecks permissions and approval; its only effect is a simulated database record. |
| 4:00–5:00 | As admin, click **Restore checkout**, reopen the checkout URL for 200, then show Grafana and `docs/status.md`. | Recovery stops new 503s; the incident is not auto-resolved. Distinguish observed HTTP batches from the older synthetic fixture and remaining test gates. |

If you need a fully deterministic fallback, **Replay synthetic failure** remains available as a separate fixture. It is labelled synthetic in the UI. Do not describe the target as a production checkout service or the simulated workflow as a real restart.
