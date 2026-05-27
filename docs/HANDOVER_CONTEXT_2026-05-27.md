# MystMon Handover Context

Date: 2026-05-27

## Repository

- GitHub repo: `https://github.com/sundeepgoel72/myst-monitor`
- Active branch: `codex/mystmon-docker-api`
- Latest published commit at handover: `b0f163b` (`List every node in Telegram report`)
- Local workspace: `D:\My Projects\codexProject\mystmon`
- Dev host/workdir: `192.168.1.72:/mnt/ssd/mystmon-dev`
- Prod host/workdir: `192.168.1.72:/mnt/ssd/mystmon-prod`

## Current Runtime State

- Dev container: `mystmon-dev`
- Dev URL: `http://192.168.1.72:8073`
- Dev status checked on 2026-05-27: running for about 37 hours
- Prod container: `mystmon-prod`
- Prod URL when enabled: `http://192.168.1.72:8072`
- Prod status at handover: intentionally not running during dev validation
- Runtime data directory: `/mnt/ssd/mystmon-dev/data`
- SQLite DB: `/mnt/ssd/mystmon-dev/data/mystmon.db`
- Latest JSON snapshot: `/mnt/ssd/mystmon-dev/data/latest.json`
- SNMP text output: `/mnt/ssd/mystmon-dev/data/snmp_extend.txt`

Latest live dev validation on 2026-05-27:

```text
health: {"status":"ok","version":"0.72.0"}
collections: 57
node_metrics: 459
telegram_reports: 3
latest fleet nodes: 8
latest online nodes: 7
latest fleet earnings_total: 216.1056268558876
latest average quality: 2.42125
```

## Implemented Capabilities

- Dockerized FastAPI collector.
- Dev/prod Compose split.
- MYST Docker inventory from `.72` through the read-only Docker socket.
- Remote Docker inventory over SSH for `.173`, `.174`, `.175`, and `.176`.
- MystNodes portal polling through `https://my.mystnodes.com`.
- Configurable portal API throttling and retries.
- Local IP matching from portal node data to local/remote Docker containers.
- Prometheus endpoint at `/metrics`.
- JSON snapshot endpoint and file output.
- SNMP-friendly text output.
- SQLite history persistence after every collection.
- SQLite-backed overall and per-node history APIs.
- Direct Telegram Bot API integration.
- Daily Telegram report at 8 AM IST with overall and every-node earnings/health deltas.

## Important Endpoints

Dev base URL:

```text
http://192.168.1.72:8073
```

Core endpoints:

```text
GET  /health
GET  /api/v1/config
GET  /api/v1/snapshot
POST /api/v1/collect
GET  /metrics
```

SQLite/history endpoints:

```text
GET /api/v1/history/latest
GET /api/v1/history/overall?limit=100
GET /api/v1/history/delta?hours=24
GET /api/v1/history/nodes
GET /api/v1/history/nodes?latest_only=false&limit=100
GET /api/v1/history/nodes/{node}?limit=100
```

Telegram endpoints:

```text
POST /api/v1/telegram/test
POST /api/v1/telegram/report?hours=24
```

## Configuration And Secrets

Most non-secret configuration is embedded in `docker-compose.dev.yml` through `MYSTMON_CONFIG_YAML`.

Secrets are intentionally not committed. Dev secrets live in:

```text
/mnt/ssd/mystmon-dev/.env
```

Expected secret keys:

```text
MYSTMON_SSH_PASSWORD
MYSTNODES_EMAIL
MYSTNODES_PASSWORD
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Telegram token/chat were copied from the existing Telegram bridge secret files into the untracked MystMon dev `.env`. MystMon only sends Telegram messages through `sendMessage`; it does not poll `getUpdates`, so it does not conflict with the Telegram bridge polling bot.

## Collection And Reporting Behavior

- Dev collection interval is controlled by `MYSTMON_POLL_INTERVAL_SECONDS` in Compose/env.
- Current dev default is hourly.
- Every collection writes:
  - `latest.json`
  - `snmp_extend.txt`
  - SQLite `collections`
  - SQLite `node_metrics`
- Daily Telegram report runs at `08:00` Asia/Kolkata.
- Duplicate daily reports are prevented by the `telegram_reports` SQLite table.
- Forced report testing is available through `POST /api/v1/telegram/report?hours=24`.
- Each Telegram report now lists every node with:
  - online/offline state
  - current earnings and delta
  - current quality and delta
  - restart count and delta
  - warning/error count and delta

## Current Fleet Notes

Known target fleet remains 8 portal nodes:

| Node | Current note |
| --- | --- |
| `1.x-hp400` | Online in latest portal/dev report. |
| `2.x-hp400` | Online in latest portal/dev report. |
| `3.72-Tower` | Online in latest portal/dev report. |
| `4.x-minipc` | Portal node present; historically linked to `.174`/VLAN14 reachability issues. |
| `5.72 - rpi` | Online in latest portal/dev report. |
| `6.x` | Online in latest portal/dev report. |
| `7.x-hp400` | Online in latest portal/dev report. |
| `8.x-hp400` | Online in latest portal/dev report. |

Latest live summary showed 8 nodes and 7 online. Keep `.174`/VLAN14 reachability on the watch list because earlier fleet validation had an unreachable placeholder for `192.168.1.174`.

## Operational Boundaries

- Do not unlock MYST identities.
- Do not alter wallet/account state.
- Do not reset node identity.
- Do not broadly restart Docker on `.72`.
- Prefer read-only checks first:
  - `docker ps`
  - `docker logs`
  - `docker inspect`
  - `docker network inspect`
  - `df -h`
- Restart only `mystmon-dev` while iterating on dev.
- Leave `mystmon-prod` stopped until explicitly promoted.

## Common Commands

Deploy current branch to dev:

```powershell
.\ops\build-on-linux.ps1 -Start
```

Manual dev validation on `.72`:

```bash
cd /mnt/ssd/mystmon-dev
curl -fsS http://127.0.0.1:8073/health
curl -fsS -X POST http://127.0.0.1:8073/api/v1/collect
curl -fsS 'http://127.0.0.1:8073/api/v1/history/overall?limit=1'
curl -fsS 'http://127.0.0.1:8073/api/v1/history/nodes'
curl -fsS 'http://127.0.0.1:8073/metrics'
```

Check SQLite counts:

```bash
python3 - <<'PY'
import sqlite3
conn=sqlite3.connect('/mnt/ssd/mystmon-dev/data/mystmon.db')
for table in ['collections','node_metrics','telegram_reports']:
    print(table, conn.execute(f'select count(*) from {table}').fetchone()[0])
PY
```

Send a forced Telegram report:

```bash
curl -fsS -X POST 'http://127.0.0.1:8073/api/v1/telegram/report?hours=24'
```

## Next Actions

1. Let the SQLite DB accumulate multiple days of samples and confirm Telegram deltas are no longer `unknown`.
2. Confirm whether `4.x-minipc` / `.174` should be treated as restored, intermittent, or still operationally degraded.
3. Decide whether to publish/promote a new Docker image tag after dev burn-in.
4. When ready, update prod Compose/image and start `mystmon-prod` on port `8072`.
5. Wire Prometheus/Grafana or SNMP consumers to prod once prod is promoted.
