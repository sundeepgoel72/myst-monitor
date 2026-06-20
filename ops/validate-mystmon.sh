#!/usr/bin/env bash
set -euo pipefail

base_url="${MYSTMON_VALIDATE_URL:-http://127.0.0.1:8072}"

curl --fail --silent --show-error "$base_url/health" >/dev/null
