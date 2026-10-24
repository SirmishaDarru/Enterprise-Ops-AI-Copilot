#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 2 ]]; then echo 'Usage: bash scripts/restore_to_new_db.sh BACKUP.dump NEW_DB_NAME' >&2; exit 2; fi
backup="$1"
dest="$2"
[[ -f "$backup" ]] || { echo "No backup: $backup" >&2; exit 2; }
[[ "$dest" =~ ^[a-zA-Z][a-zA-Z0-9_]{0,62}$ ]] || { echo 'Use a simple database name of up to 63 characters' >&2; exit 2; }
[[ "$dest" != ops_copilot ]] || { echo 'Destination must differ from the live database' >&2; exit 2; }
cd "$(dirname "$0")/.."
if docker compose exec -T db psql -U ops_app -d postgres -Atqc "SELECT 1 FROM pg_database WHERE datname = '$dest'" | grep -q '^1$'; then
  echo "Database already exists: $dest" >&2; exit 1
fi
docker compose exec -T db createdb -U ops_app "$dest"
docker compose exec -T db pg_restore -U ops_app --no-owner --no-acl --exit-on-error -d "$dest" < "$backup"
docker compose exec -T db psql -U ops_app -d "$dest" -Atqc 'SELECT version_num FROM alembic_version'
printf 'Restored into new database: %s\n' "$dest"
