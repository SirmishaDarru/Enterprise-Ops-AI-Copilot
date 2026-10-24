#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
output="${1:-backups/ops-copilot-$(date -u +%Y%m%dT%H%M%SZ).dump}"
if [[ -e "$output" ]]; then echo "Backup exists: $output" >&2; exit 1; fi
if ! docker compose exec -T db pg_dump -U ops_app -d ops_copilot -Fc -Z 6 > "$output"; then
  rm -f "$output"
  exit 1
fi
docker compose exec -T db pg_restore -l < "$output" >/dev/null
printf 'Backup created: %s\n' "$output"
