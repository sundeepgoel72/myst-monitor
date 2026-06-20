#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$repo_dir"
test -f .env || {
  echo "Missing $repo_dir/.env. Create it from .env.example and fill local secrets locally." >&2
  exit 1
}

if [[ "${MYSTMON_SKIP_PULL:-0}" != "1" ]]; then
  docker compose pull mystmon-prod
fi
./ops/bootstrap-mystmon-storage.sh
docker start mystmon-registry >/dev/null 2>&1 || true
docker compose up -d mystmon-prod
for i in 1 2 3 4 5 6 7 8 9 10; do
  status="$(docker inspect -f '{{.State.Health.Status}}' mystmon-prod 2>/dev/null || true)"
  if [[ "$status" == "healthy" ]]; then
    break
  fi
  if [[ "$status" == "unhealthy" ]]; then
    docker compose ps mystmon-prod
    exit 1
  fi
  sleep 3
done
./ops/validate-mystmon.sh
docker compose ps mystmon-prod
docker stop mystmon-registry >/dev/null 2>&1 || true
