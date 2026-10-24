# Git Bash and Docker troubleshooting

Use the folder containing `compose.yaml` as the working directory for every Compose command. In Git Bash, use `cd`, `cp` and `export`; `Set-Location` and `Copy-Item` are PowerShell commands. If you see `no configuration file provided`, run `pwd` and `ls compose.yaml` first. An extracted ZIP should have `compose.yaml` at its root, not inside another folder you have not entered.

| Symptom | Check and action |
| --- | --- |
| `docker: command not found` or daemon connection error | Start Docker Desktop, then run `docker version` and `docker compose version` in a fresh Git Bash window. |
| `uv: command not found` | From `backend` use `py -3.12 -m pip install --user uv`, then `py -3.12 -m uv sync --frozen --extra dev`. This invokes the module even if `uv` is not on PATH. |
| `backend/.env` missing | On a **fresh** install, copy `backend/.env.example`; generate a secret as in `README.md`. On upgrade, restore your existing private `.env` rather than overwriting it. |
| API fails while `db` is healthy | Check `docker compose --profile full logs --tail=80 migrate api`. Ensure the backend `.env` has a valid `JWT_SECRET`; then `docker compose --profile full exec -T api alembic current` should show `0005_workflows`. Avoid sharing secret values. |
| App opens but login fails | Seed accounts with a password of 12+ characters. If accounts already exist, run the explicit reset command below; ordinary seeding does not change existing hashes. |
| Workflow remains `queued` or `running` | Check `docker compose --profile full logs --tail=80 worker`, the `db` health and the worker metrics in Grafana. The worker must be running; lease recovery and retries are bounded. |
| Report runner says wrong provider | Set `INVESTIGATION_PROVIDER=mock` in private `backend/.env`, then recreate API with `docker compose --profile full up -d --force-recreate api`; rerun the review. A live provider is deliberately rejected by the review script. |
| Runbook source missing from investigation | Check Knowledge search under the responder account. If you changed `EMBEDDING_MODE`, reindex the demo documents from Knowledge, or keep the mode used when they were indexed. First use of local embeddings may require a model download; mock mode is deterministic. |
| `TEST_DATABASE_URL` tests skipped | Set that variable to a **migrated PostgreSQL** database URL for the one test command. Skips are expected without it. Do not paste credentials into chat. |
| Previous data seems gone after moving folders | Compose derives its project name from the folder; inspect `docker compose ls` and `docker volume ls`. Reuse the old project name with `docker compose -p OLD_PROJECT_NAME ...` from the new folder. Do not delete volumes while diagnosing. |
| Port already allocated | Stop the earlier local API/frontend or the other Compose project holding 5432, 8080, 3000, 9090 or 16686. `docker compose ps` helps identify the active stack. |

## Explicit local password reset

Run from the project root in Git Bash after the `api` service is running. This sets a newly entered password on all four existing local demo users; it is restricted to `APP_ENV=development` and is never run automatically:

```bash
read -r -s -p 'New local demo password (12+ chars): ' DEMO_PASSWORD
printf '\n'
export DEMO_PASSWORD
docker compose --profile full exec -T -e DEMO_PASSWORD="$DEMO_PASSWORD" api python -m app.seed --reset-password
unset DEMO_PASSWORD
```

If a command errors before `unset`, run `unset DEMO_PASSWORD` manually. This password is used only for local demo identities. If running the backend directly from `backend`, use `py -3.12 -m uv run --frozen python -m app.seed --reset-password` with `DEMO_PASSWORD` set in that shell.

## Backup and safe shutdown

`docker compose down` preserves volumes. `docker compose down -v` deletes them. From the project root use `bash scripts/backup.sh`, then `bash scripts/restore_to_new_db.sh backups/ACTUAL_FILE.dump ops_restore_check`. Restore refuses an existing destination and prints its migration revision. A database dump contains account hashes and any stored documents, so keep it private. This backup is a manual logical dump, not a scheduled recovery system.

## Stage 10 checkout service

If the live panel says unavailable, run `docker compose --profile full --profile observability ps` and `docker compose --profile full logs --tail=80 checkout-demo checkout-traffic checkout-collector api`. Check `api` migration is `0006_live_demo_cursor`. The checkout service is internal; only the public checkout action is proxied at `http://localhost:8080/checkout-demo/checkout`.

If checkout returns 503 unexpectedly, sign in as admin and click **Restore checkout**. If the live service card exists but no new samples arrive, inspect collector logs. A buffer gap warning means some short-lived events were lost before polling; do not treat that batch as complete telemetry. If the incident investigation lacks a runbook source, click **Load live runbook** again and verify your configured embedding mode can index it. The controlled failure itself does not auto-resolve the incident.
