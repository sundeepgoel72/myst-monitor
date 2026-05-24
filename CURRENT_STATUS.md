# MystMon Current Status Report

Date: 2026-05-24

## Executive Summary

MystMon `0.72` has been updated for the new dev/prod deployment layout. The Windows workspace is now under `D:\My Projects\codexProject\mystmon`; `.72` dev is deployed from `/mnt/ssd/mystmon-dev` on port `8073`, and `.72` prod is staged at `/mnt/ssd/mystmon-prod` for Docker Hub image pulls on port `8072`.

The collector is working for the reachable fleet. Current validation finds 7 real MYST containers plus one unreachable placeholder for `192.168.1.174`. The configured target is 8 containers, so validation correctly remains partial until `.174` is back online or its current MYST container can be inventoried.

## Repository State

- Workspace: `D:\My Projects\codexProject\mystmon`
- Branch: `codex/mystmon-docker-api`
- Working tree before this report: clean
- Current deployment commit: `7bb842f`
- Latest commits:
  - `19ee6da` Use POSIX MYST container pattern
  - `622361a` Add remote MYST host inventory
  - `8198ed8` Use published image install flow
  - `df9096b` Add TequilAPI based Myst metrics
  - `09c9ec7` Align MystMon with MYST node handover
  - `0f9cda0` Add Linux build host workflow
  - `87e812a` Create MystMon 0.72 Docker monitoring service

## Implemented Capabilities

- Dockerized FastAPI collector.
- Docker Compose install flow that pulls a published image.
- Local Docker inventory on `.72` via read-only Docker socket.
- Remote read-only Docker inventory over SSH for `.173`, `.174`, `.175`, and `.176`.
- Prometheus `/metrics` endpoint.
- JSON snapshot at `/data/mystmon/latest.json`.
- SNMP-friendly text output at `/data/mystmon/snmp_extend.txt`.
- Optional MYST TequilAPI probing based on current official MYST documentation.
- Six-hour collection support through ops scripts and scheduler assets.
- Validation script for health, metrics, snapshot, and expected node count.

## Current Deployment On `.72`

- Host: `192.168.1.72`
- Prod directory: `/mnt/ssd/mystmon-prod`
- Dev directory: `/mnt/ssd/mystmon-dev`
- Prod container: `mystmon-prod`
- Dev container: `mystmon-dev`
- Prod image: `docker.io/sundeep/mystmon:0.72`
- Runtime: Docker Compose with `network_mode: host`
- Prod service port: `8072`
- Dev service port: `8073`
- Current dev container status: running
- Current prod status: staged, but Docker Hub pull is blocked until `docker.io/sundeep/mystmon:0.72` exists or Docker Hub auth is configured
- Previous container still present: `mystmon` from `localhost:5050/mystmon:0.72`

Because the container uses host networking, `docker compose ps` does not show a normal published `PORTS` mapping. The service listens directly on the host through `MYSTMON_PORT=8072`.

## Latest Validation Result

Command used on `.72`:

```bash
cd /mnt/ssd/mystmon-dev
MYSTMON_BASE_URL=http://127.0.0.1:8073 MYSTMON_DATA_DIR=/mnt/ssd/mystmon-dev/data bash ops/validate-mystmon.sh
```

Result:

- Dev health endpoint is reachable.
- Collection triggered successfully.
- Snapshot generated successfully.
- Metrics endpoint is reachable through the validation path.
- Real reachable MYST containers found: 7.
- Configured expected count: 8.
- Validation result: partial/failing because `.174` is unreachable.

Current node inventory:

| Host | Container | Status | Restarts |
| --- | --- | --- | --- |
| `192.168.1.72` | `myst.18.x` | running | 0 |
| `192.168.1.72` | `myst.17.x` | running | 0 |
| `192.168.1.72` | `myst.12.x` | running | 0 |
| `192.168.1.72` | `myst.1.x` | running | 0 |
| `192.168.1.173` | `myst13.x` | running | 0 |
| `192.168.1.174` | `unreachable-192.168.1.174` | unreachable placeholder | 0 |
| `192.168.1.175` | `myst` | running | 1 |
| `192.168.1.176` | `myst.16.x` | running | 0 |

## Known Gaps / Risks

- `192.168.1.174` is still unreachable, previously failing with `No route to host`. This blocks full 8-node validation.
- MYST TequilAPI metrics are implemented, but API metrics depend on TequilAPI being reachable or mapped for the individual MYST containers. Current validation primarily confirms Docker/log/fleet inventory.
- The `.72` runtime `.env` contains deployment/runtime secrets and is intentionally not committed. Longer-term, SSH key auth would be cleaner than a stored SSH password for remote inventory.
- Prod Compose now defaults to Docker Hub image `docker.io/sundeep/mystmon:0.72`, but `.72` cannot pull it yet: access denied or repository unavailable.
- Existing MYST identity signing warnings were observed earlier on local MYST logs. No identity unlock or wallet/account action has been taken.

## Next Actions

1. Restore network reachability for `192.168.1.174`.
2. Re-run MystMon validation and confirm all 8 real MYST containers are found.
3. Publish `docker.io/sundeep/mystmon:0.72` to Docker Hub or run `docker login` on `.72` if the repository is private.
4. Replace password-based remote inventory with SSH keys if this will run long term.
5. Wire Prometheus or SNMP polling into the existing monitoring stack using `http://192.168.1.72:8072/metrics` or `/mnt/ssd/mystmon-prod/data/snmp_extend.txt`.
