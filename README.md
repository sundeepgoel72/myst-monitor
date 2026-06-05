# MystMon 0.74

MystMon is a lightweight monitoring service for MYST passive-income nodes. It polls local Docker containers, optional TequilAPI endpoints, and optional MystNodes portal data, then exposes the results through a web UI, Prometheus metrics, JSON snapshots, and SNMP-friendly text output.

## License

Apache License 2.0. See [LICENSE](LICENSE) for the full text.

## Features

- Docker-based service with `docker compose`
- REST API with OpenAPI docs at `/docs`
- Web UI at `/ui` with dashboard, fleet, history, and settings pages
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

## Docker Modes

MystMon supports two common Docker workflows:

- Development: use `docker-compose.dev.yml` to build from local source.
- Production or deployment: use `docker-compose.yml` to run the published image.

Use the same tracked `config.yaml` baseline in both modes, and put machine-specific values in `config.local.yaml` when needed. The local override file is ignored by git and is merged automatically when present.

## Coordination

When a change needs tracking beyond the code itself, create or update a Git issue as part of the normal workflow. Keep the issue reference in the handover or worklog so the next session can pick up the same thread.

Open the API locally after starting the service:

```text
http://<mystmon-host>:8072/docs
http://<mystmon-host>:8072/ui
http://<mystmon-host>:8072/metrics
```

## Configuration

MystMon reads `config.yaml` by default and will also merge `config.local.yaml` when it exists beside it. Keep the tracked example file as the shared baseline, and put machine-specific or secret values in the ignored local override.

UI settings can be customized with the `ui` section:

```yaml
ui:
  enabled: true
  path: /ui
  auto_refresh_interval_seconds: 30
  max_history_points: 500
  theme: system
```

The default container and host lists are intentionally conservative. Update them to match your own deployment:

- container names
- container host addresses
- remote host credentials
- SNMP targets
- local config overrides

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
  wallet_address: 0x9A183F79b7b803DF658DB0aC6159f0016e9db4bE
```

When you need local-only values, create `config.local.yaml` alongside `config.yaml` and keep it out of git. The local file overrides matching keys from the tracked config, so you can test safely without editing the committed example.

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
- `config.local.yaml` is the preferred local override file for development and testing.
- The UI is available at `/ui` when `ui.enabled` is true.

## Testing

Run the full test suite locally with:

```bash
pytest
```

The GitHub Actions workflow at `.github/workflows/test.yml` runs the same test suite and a `ruff` check on pushes and pull requests to the main development branches.

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
