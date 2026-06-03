#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

tmp_service="$(mktemp)"
tmp_timer="$(mktemp)"
trap 'rm -f "$tmp_service" "$tmp_timer"' EXIT
sed "s|__REPO_DIR__|$repo_dir|g" "$repo_dir/ops/mystmon.service" > "$tmp_service"
sed "s|__REPO_DIR__|$repo_dir|g" "$repo_dir/ops/mystmon.timer" > "$tmp_timer"

sudo install -m 0644 "$tmp_service" /etc/systemd/system/mystmon.service
sudo install -m 0644 "$tmp_timer" /etc/systemd/system/mystmon.timer
sudo systemctl daemon-reload
sudo systemctl enable --now mystmon.timer
systemctl list-timers mystmon.timer
