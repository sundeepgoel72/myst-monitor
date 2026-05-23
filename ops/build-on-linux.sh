#!/usr/bin/env bash
set -euo pipefail

host="${MYSTMON_BUILD_HOST:-192.168.1.72}"
user="${MYSTMON_BUILD_USER:-}"
remote_dir="${MYSTMON_REMOTE_DIR:-~/mystmon}"
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
ssh "$target" "cd $remote_dir && tar -xf mystmon-build.tar && docker compose build"

if [[ "$start" == "--start" ]]; then
  ssh "$target" "cd $remote_dir && docker compose up -d"
fi

echo "MystMon build completed on $target in $remote_dir"
