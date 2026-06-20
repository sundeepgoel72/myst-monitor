# MystMon

[![License](https://img.shields.io/github/license/sundeepgoel72/myst-monitor)](LICENSE)
[![Version](https://img.shields.io/github/v/tag/sundeepgoel72/myst-monitor?label=version)](https://github.com/sundeepgoel72/myst-monitor/tags)
[![Tests](https://img.shields.io/github/actions/workflow/status/sundeepgoel72/myst-monitor/test.yml?branch=main&label=tests)](https://github.com/sundeepgoel72/myst-monitor/actions/workflows/test.yml)

MystMon is a read-only monitoring service for MYST nodes. It collects runtime and portal state, writes snapshots and CSV exports, exposes an HTTP API and Prometheus metrics, and supports a lightweight web UI for inspection.

## Core Capabilities

- Read-only TequilAPI monitoring for local and remote MYST runtimes
- MystNodes portal collection for account, node, wallet, and runtime matching data
- Snapshot and SQLite history storage with local-time timestamps driven by `service.timezone`
- CSV exports for accounts, portal nodes, local runtimes, and local hosts
- HTTP API, Prometheus metrics, and optional UI for operational inspection

## Run From Published Docker Image

Docker is for packaging and deployment only. It is not the day-to-day development or debugging path.

Pull the published dev image:

```bash
docker pull ghcr.io/sundeepgoel72/mystmon:dev
```

Prepare config and data locally:

```bash
cp config.example.yaml config.yaml
cp config.local.example.yaml config.local.yaml
mkdir -p data
```

Run the container:

```bash
docker run -d \
  --name mystmon-dev \
  --restart unless-stopped \
  -p 8072:8072 \
  -e MYSTMON_DATA_DIR=/data/mystmon \
  -e MYSTMON_CONFIG=/app/config.yaml \
  -e MYSTMON_HOST=0.0.0.0 \
  -e MYSTMON_PORT=8072 \
  -e MYSTMON_TEQUILAPI_PASSWORD=your_tequilapi_password \
  -e MYSTMON_SSH_PASSWORD=your_ssh_password \
  -v "$PWD/config.yaml:/app/config.yaml:ro" \
  -v "$PWD/config.local.yaml:/app/config.local.yaml:ro" \
  -v "$PWD/data:/data/mystmon" \
  ghcr.io/sundeepgoel72/mystmon:dev
```

Health check:

```bash
curl http://127.0.0.1:8072/health
```

Container outputs are written under `/data/mystmon` inside the container, backed by your mounted `data/` directory.

## Configuration Model

Tracked base config:
- [config.example.yaml](config.example.yaml)

Local override template:
- [config.local.example.yaml](config.local.example.yaml)

Runtime behavior:
- copy `config.example.yaml` to `config.yaml` for your working config
- copy `config.local.example.yaml` to `config.local.yaml` for host- or credential-specific overrides
- keep secrets in environment variables or untracked local files

Important configuration areas:
- `service`: polling, paths, timezone
- `myst`: local runtime and remote TequilAPI probe settings
- `mystnodes_accounts`: MystNodes portal account configuration
- `outputs`: latest snapshot, SNMP text, and CSV export paths
- `history`: SQLite history storage
- `telegram`, `ui`, `alerting`: optional service features

## WSL Development Setup From Source

WSL is the default environment for coding, testing, and debugging.

```bash
git clone https://github.com/sundeepgoel72/myst-monitor.git
cd myst-monitor
cp config.example.yaml config.yaml
cp config.local.example.yaml config.local.yaml
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Verify imports:

```bash
.venv/bin/python -c "import mystmon.api; print('ok')"
```

## Testing And Validation

Focused validation used in this repo:

```bash
PYTHONPATH=. .venv/bin/pytest tests/test_release_validation.py -q
PYTHONPATH=. .venv/bin/pytest \
  tests/test_release_validation.py \
  tests/test_config.py \
  tests/test_main.py \
  tests/test_history.py \
  tests/test_scheduler.py \
  tests/test_export_csv.py \
  tests/test_mystnodes_collector.py \
  tests/test_myst_local_discovery.py -q
```

Run the full suite:

```bash
PYTHONPATH=. .venv/bin/pytest
```

Shell syntax validation for deployment helpers:

```bash
bash -n ops/build-on-linux.sh ops/install-remote.sh ops/validate-mystmon.sh
```

## Deployment Notes

- Canonical branch: `main`
- Current app version: `0.1`
- Versioning rule: increment by `0.01` for each minor release
- GHCR publish target:
  - `ghcr.io/sundeepgoel72/mystmon:dev` from pushes to `main`
  - `ghcr.io/sundeepgoel72/mystmon:<version>` from tags such as `v0.1`
- If the package page shows stale metadata, check the latest `Publish Docker Image` workflow run first. GHCR metadata updates only after a successful image push.

## Documentation

- [docs/API.md](docs/API.md) - API surface and history endpoints
- [docs/TEQUILAPI.md](docs/TEQUILAPI.md) - TequilAPI collection details
- [docs/DESIGN.md](docs/DESIGN.md) - architecture and maintainer design notes
- [.codex/HANDOVER.md](.codex/HANDOVER.md) - current maintainer handover for follow-on agents

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
