# MystMon 0.72

MystMon is a lightweight monitoring service for the MYST passive income nodes. It is designed to run on the HP400 management host at `192.168.1.72` from `/mnt/ssd/codex/mystmon`, poll local Docker containers every 6 hours, and expose status through Prometheus, JSON, and SNMP-friendly text output.

## Features

- Docker-installable service with `docker compose`
- REST API with OpenAPI docs at `/docs`
- Prometheus-compatible `/metrics` endpoint
- Docker/log collector for MYST containers
- Optional MYST TequilAPI metrics when mapped locally
- SNMP-style status file for `snmpd extend` or Telegraf exec input
- JSON snapshot at `/data/mystmon/latest.json`
- YAML configuration with environment overrides

## Quick Start

On `192.168.1.72`:

```bash
mkdir -p /mnt/ssd/codex
cd /mnt/ssd/codex
git clone <your-repo-url> mystmon
cd mystmon
cp .env.example .env
vi .env
docker compose pull mystmon
docker compose up -d mystmon
```

Then open:

```text
http://192.168.1.72:8072/docs
http://192.168.1.72:8072/metrics
```

From this Windows workspace, after SSH is configured:

```powershell
.\ops\build-on-linux.ps1 -Start
```

## Configuration

MystMon reads `config.yaml` by default. The committed default targets the known MYST containers on `192.168.1.72`:

- `myst.1.x`
- `myst.12.x`
- `myst.17.x`
- `myst.18.x`

```yaml
service:
  name: mystmon
  poll_interval_seconds: 21600
  log_window_seconds: 21600

myst:
  enabled: true
  docker_socket: unix:///var/run/docker.sock
  api_probe_enabled: true
  api_endpoints:
    - name: healthcheck
      path: /healthcheck
      metric_prefix: health

outputs:
  latest_json_path: /data/mystmon/latest.json
  snmp_extend_path: /data/mystmon/snmp_extend.txt
```

`poll_interval_seconds: 21600` polls once every 6 hours.

## MYST Collection

MystMon gathers read-only data only:

- container running state
- restart count
- uptime
- Docker networks and IPs
- mapped ports
- recent log counts for errors, warnings, promises, sessions, settlement/auth/unlock patterns
- optional TequilAPI `/healthcheck` state
- optional TequilAPI metrics from documented read-only surfaces

It does not unlock identities, store MYST passwords, change wallet state, or restart MYST containers.

TequilAPI is treated as optional because the current MYST docs describe it as a powerful local REST API that defaults to port `4050`, exposes Swagger under `/docs`, and includes read-only surfaces such as `/healthcheck`, `/identities`, `/services/*`, `/sessions/*`, `/node/provider/*`, `/location`, and `/nat/type`. Keep it bound locally unless you intentionally secure and expose it.

MystMon’s default API endpoint list is read-only and tolerant: unavailable, unauthorized, or absent endpoints are recorded as down rather than failing the whole collection pass.

Default API-derived Prometheus metrics are exposed as:

- `mystmon_node_api_up{node=...}`
- `mystmon_node_api_endpoint_up{node=...,endpoint=...}`
- `mystmon_node_api_metric{node=...,metric=...}`
- `mystmon_node_api_info{node=...,key=...,value=...}`

If your nodes require TequilAPI Basic Auth, set this in `config.yaml`:

```yaml
myst:
  api_username: myst
  api_password_env: MYSTMON_TEQUILAPI_PASSWORD
```

Then set `MYSTMON_TEQUILAPI_PASSWORD` in the environment on `.72`. MystMon does not require or store MYST identity unlock passwords.

References:

- [MystNodes TequilAPI help](https://help.mystnodes.com/en/articles/4531943-tequilapi)
- [Mysterium node development docs](https://docs.mysterium.network/for-developers/node-development)

## Docker Compose Profiles

Run the MystMon service:

```bash
docker compose up -d --build
```

Run with an included Prometheus server:

```bash
docker compose --profile prometheus up -d --build
```

## SNMP Integration

The compact text output is written to:

```text
/mnt/ssd/codex/mystmon/data/snmp_extend.txt
```

Example `snmpd` extend entry:

```text
extend mystmon /bin/cat /mnt/ssd/codex/mystmon/data/snmp_extend.txt
```

Telegraf can also read the same file with an `inputs.exec` command.

## Linux Build Host

This repo is configured to use `192.168.1.72` as the Linux build host. The helper scripts copy the current Git commit to `/mnt/ssd/codex/mystmon` over SSH and run the Docker build there.

From Windows PowerShell:

```powershell
.\ops\build-on-linux.ps1
```

Build and start the service on the Linux host:

```powershell
.\ops\build-on-linux.ps1 -Start
```

From Linux or Git Bash:

```bash
./ops/build-on-linux.sh
./ops/build-on-linux.sh --start
```

Optional environment overrides:

```text
MYSTMON_IMAGE=ghcr.io/<owner>/mystmon:0.72
MYSTMON_EXPECTED_NODE_COUNT=8
MYSTMON_BUILD_HOST=192.168.1.72
MYSTMON_BUILD_USER=
MYSTMON_REMOTE_DIR=/mnt/ssd/codex/mystmon
MYSTMON_TEQUILAPI_PASSWORD=
MYSTNODES_EMAIL=
MYSTNODES_PASSWORD=
```

SSH access to `192.168.1.72` must be configured before running the remote build.

## Publishing

The install compose file expects a published image repository:

```text
MYSTMON_IMAGE=ghcr.io/<owner>/mystmon:0.72
```

Publish to an external registry manually after `docker login`:

```bash
export MYSTMON_IMAGE=ghcr.io/<owner>/mystmon:0.72
./ops/publish-image.sh
```

Or from PowerShell:

```powershell
$env:MYSTMON_IMAGE = "ghcr.io/<owner>/mystmon:0.72"
.\ops\publish-image.ps1
```

For local development builds:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build mystmon
```

The included GitHub Actions workflow publishes to GHCR on tags such as `v0.72.0`.

For a private `.72` registry fallback:

```bash
docker run -d --restart unless-stopped -p 127.0.0.1:5000:5000 --name registry registry:2
export MYSTMON_IMAGE=localhost:5000/mystmon:0.72
./ops/publish-image.sh
docker compose pull mystmon
docker compose up -d mystmon
```

## Validation On `.72`

After install on `192.168.1.72`:

```bash
cd /mnt/ssd/codex/mystmon
set -a
. ./.env
set +a
./ops/validate-mystmon.sh
```

The validator triggers a collection, checks `/api/v1/snapshot`, expects `8` MYST containers by default, checks `/metrics`, and verifies both JSON and SNMP text outputs exist.

## API

Core endpoints:

- `GET /health`
- `GET /api/v1/config`
- `GET /api/v1/readings`
- `GET /api/v1/snapshot`
- `POST /api/v1/collect`
- `GET /metrics`

The full API documentation is generated by FastAPI at `/docs` and `/openapi.json`.

## Git Install

```powershell
git clone <your-repo-url> /mnt/ssd/codex/mystmon
cd /mnt/ssd/codex/mystmon
cp .env.example .env
vi .env
docker compose pull mystmon
docker compose up -d mystmon
```
