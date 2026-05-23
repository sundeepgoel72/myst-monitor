#!/usr/bin/env bash
set -euo pipefail

repo_dir="${MYSTMON_REMOTE_DIR:-/mnt/ssd/codex/mystmon}"

cd "$repo_dir"
test -f .env || {
  echo "Missing $repo_dir/.env. Create it from .env.example and fill local secrets on .72." >&2
  exit 1
}

docker compose pull mystmon
docker compose up -d mystmon
./ops/validate-mystmon.sh
docker compose ps mystmon
