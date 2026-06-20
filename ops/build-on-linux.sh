#!/usr/bin/env bash
set -euo pipefail

host="${MYSTMON_BUILD_HOST:?Set MYSTMON_BUILD_HOST to the SSH host}"
user="${MYSTMON_BUILD_USER:-}"
remote_dir="${MYSTMON_REMOTE_DIR:?Set MYSTMON_REMOTE_DIR to the remote install path}"
start="${1:-}"

target="$host"
if [[ -n "$user" ]]; then
  target="$user@$host"
fi

archive="$(mktemp -t mystmon-build.XXXXXX.tar)"
trap 'rm -f "$archive"' EXIT

git archive --format=tar --output="$archive" HEAD
ssh "$target" "mkdir -p $remote_dir"
scp "$archive" "$target:$remote_dir/mystmon-build.tar"
ssh "$target" "cd $remote_dir && tar -xf mystmon-build.tar && test -f config.yaml && ./ops/bootstrap-mystmon-storage.sh && if [ \"\${MYSTMON_SKIP_PULL:-0}\" != 1 ]; then docker compose pull mystmon; fi"

if [[ "$start" == "--start" ]]; then
  ssh "$target" "cd $remote_dir && docker compose up -d mystmon && for i in 1 2 3 4 5 6 7 8 9 10; do status=\$(docker inspect -f '{{.State.Health.Status}}' mystmon 2>/dev/null || true); if [ \"\$status\" = healthy ]; then break; fi; if [ \"\$status\" = unhealthy ]; then docker compose ps mystmon; exit 1; fi; sleep 3; done; ./ops/validate-mystmon.sh && docker compose ps mystmon"
fi

echo "MystMon install completed on $target in $remote_dir"
