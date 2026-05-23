#!/usr/bin/env bash
set -euo pipefail

repo_dir="${MYSTMON_REMOTE_DIR:-/mnt/ssd/codex/mystmon}"

sudo install -m 0644 "$repo_dir/ops/mystmon.service" /etc/systemd/system/mystmon.service
sudo install -m 0644 "$repo_dir/ops/mystmon.timer" /etc/systemd/system/mystmon.timer
sudo systemctl daemon-reload
sudo systemctl enable --now mystmon.timer
systemctl list-timers mystmon.timer
