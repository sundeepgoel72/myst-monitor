#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$repo_dir"
test -f .env || {
  echo "Missing $repo_dir/.env. Create it from .env.example and fill local secrets locally." >&2
  exit 1
}

docker compose pull mystmon
docker compose up -d mystmon
./ops/validate-mystmon.sh
docker compose ps mystmon
