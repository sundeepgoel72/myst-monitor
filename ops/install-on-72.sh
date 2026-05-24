#!/usr/bin/env bash
set -euo pipefail

repo_dir="${MYSTMON_PROD_DIR:-/mnt/ssd/mystmon-prod}"
service="${MYSTMON_SERVICE:-mystmon-prod}"
base_url="${MYSTMON_BASE_URL:-http://127.0.0.1:8072}"

cd "$repo_dir"
test -f .env || {
  echo "Missing $repo_dir/.env. Create it from .env.example and fill local secrets on .72." >&2
  exit 1
}

docker compose pull "$service"
docker compose up -d "$service"
MYSTMON_BASE_URL="$base_url" MYSTMON_DATA_DIR="$repo_dir/data" ./ops/validate-mystmon.sh
docker compose ps "$service"
