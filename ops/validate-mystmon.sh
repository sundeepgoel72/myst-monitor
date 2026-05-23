#!/usr/bin/env bash
set -euo pipefail

expected="${MYSTMON_EXPECTED_NODE_COUNT:-8}"
base_url="${MYSTMON_BASE_URL:-http://127.0.0.1:8072}"

echo "Triggering MystMon collection..."
curl -fsS -X POST "$base_url/api/v1/collect" >/tmp/mystmon-collect.json
cat /tmp/mystmon-collect.json
echo

echo "Fetching snapshot..."
curl -fsS "$base_url/api/v1/snapshot" >/tmp/mystmon-snapshot.json

actual="$(python3 - <<'PY'
import json
with open("/tmp/mystmon-snapshot.json", "r", encoding="utf-8") as handle:
    snapshot = json.load(handle)
nodes = snapshot.get("nodes", [])
print(len(nodes))
for node in nodes:
    print(f"{node.get('name')} running={node.get('running')} restarts={node.get('restart_count')} api_up={(node.get('api') or {}).get('up')}")
PY
)"

echo "$actual"
count="$(echo "$actual" | head -n 1)"
if [[ "$count" != "$expected" ]]; then
  echo "Expected $expected MYST containers, found $count" >&2
  exit 1
fi

curl -fsS "$base_url/metrics" | grep -E 'mystmon_node_(running|api_up|api_metric)' | head -40
test -s /mnt/ssd/codex/mystmon/data/latest.json
test -s /mnt/ssd/codex/mystmon/data/snmp_extend.txt
echo "MystMon validation passed for $count MYST containers."
