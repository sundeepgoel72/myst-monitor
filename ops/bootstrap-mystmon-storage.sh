#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 -m mystmon.bootstrap \
  --db-path "${MYSTMON_DB_PATH:-$repo_dir/data/mystmon.db}" \
  --latest-json-path "${MYSTMON_LATEST_JSON_PATH:-$repo_dir/data/latest.json}" \
  --snmp-extend-path "${MYSTMON_SNMP_EXTEND_PATH:-$repo_dir/data/snmp_extend.txt}"
