# MystMon 0.72

MystMon is a lightweight monitoring service for MYST passive-income nodes. It polls local Docker containers, optional TequilAPI endpoints, and optional MystNodes portal data, then exposes the results through Prometheus, JSON, and SNMP-friendly text output.

## Features

- Docker-based service with `docker compose`
- REST API with OpenAPI docs at `/docs`
- Prometheus-compatible `/metrics` endpoint
- Docker/log collector for MYST containers
- Optional TequilAPI metrics from read-only endpoints
- SNMP-style text output for `snmpd extend` or Telegraf exec input
- JSON snapshot at `/data/mystmon/latest.json`
- YAML configuration with environment overrides

## Quick Start

```bash
git clone <your-repo-url> mystmon
cd mystmon
cp .env.example .env
cp config.example.yaml config.yaml
```

Edit `.env` and `config.yaml` with your local host, credential, and path values.

Open the API locally after starting the service:

```text
http://<mystmon-host>:8072/docs
http://<mystmon-host>:8072/metrics
```

## Configuration

MystMon reads `config.yaml` by default. The tracked example file contains placeholders only; keep your real values in the ignored local `config.yaml`.

The default container and host lists are intentionally conservative. Update them to match your own deployment:

- container names
- container host addresses
- remote host credentials
- SNMP targets

Example configuration highlights:

```yaml
service:
  name: mystmon
  poll_interval_seconds: 21600

myst:
  enabled: true
  local_host: localhost
  docker_socket: unix:///var/run/docker.sock
  api_probe_enabled: true
  api_default_port: 4050
```

## Collection

MystMon gathers read-only data only:

- container running state
- restart count
- uptime
- Docker networks and IPs
- mapped ports
- recent log counts
- optional TequilAPI health and metrics

It does not unlock identities, store passwords, change wallet state, or restart MYST containers.

## Build and Remote Install

The helper scripts derive the checkout path locally and expect you to provide the remote host and remote install directory through environment variables.

Example environment:

```text
MYSTMON_BUILD_HOST=<build-host>
MYSTMON_BUILD_USER=
MYSTMON_REMOTE_DIR=<remote-repo-dir>
MYSTMON_IMAGE=ghcr.io/<user>/mystmon:<tag>
```

Build from Linux or Git Bash:

```bash
./ops/build-on-linux.sh
./ops/build-on-linux.sh --start
```

Build from PowerShell:

```powershell
.\ops\build-on-linux.ps1
.\ops\build-on-linux.ps1 -Start
```

Remote install on the target host:

```bash
./ops/install-remote.sh
./ops/install-systemd-timer.sh
```

## SNMP Integration

The compact text output is written to:

```text
data/snmp_extend.txt
```

Example `snmpd` extend entry:

```text
extend mystmon /bin/cat <repo-dir>/data/snmp_extend.txt
```

## Deployment Notes

- `ops/mystmon.service` and `ops/mystmon.cron` are templates. The install scripts inject the checkout path locally before installing them.
- `ops/prometheus.yml` uses placeholder targets so you can map your own hostnames or IPs.
- `docs/PATH_MIGRATION.md` documents the local path migration flow if you previously installed from an older checkout path.

## Publishing

Set the image name before publishing:

```bash
export MYSTMON_IMAGE=ghcr.io/<user>/mystmon:<tag>
./ops/publish-image.sh
```

Or from PowerShell:

```powershell
$env:MYSTMON_IMAGE = "ghcr.io/<user>/mystmon:<tag>"
.\ops\publish-image.ps1
```

## Repository Layout

- `mystmon/` - application code
- `tests/` - unit and regression tests
- `ops/` - deployment and publish helpers
- `docs/` - public documentation

