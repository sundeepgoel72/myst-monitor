#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$repo_dir"
test -f config.yaml || {
  echo "Missing $repo_dir/config.yaml. Create it from config.example.yaml and fill runtime settings locally." >&2
  exit 1
}

if [[ "${MYSTMON_SKIP_PULL:-0}" != "1" ]]; then
  docker compose pull mystmon
fi
./ops/bootstrap-mystmon-storage.sh
docker compose up -d mystmon
for i in 1 2 3 4 5 6 7 8 9 10; do
  status="$(docker inspect -f '{{.State.Health.Status}}' mystmon 2>/dev/null || true)"
  if [[ "$status" == "healthy" ]]; then
    break
  fi
  if [[ "$status" == "unhealthy" ]]; then
    docker compose ps mystmon
    exit 1
  fi
  sleep 3
done
./ops/validate-mystmon.sh
docker compose ps mystmon
