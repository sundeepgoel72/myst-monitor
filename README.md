# MystMon

[![License](https://img.shields.io/github/license/sundeepgoel72/myst-monitor)](LICENSE)
[![Version](https://img.shields.io/github/v/tag/sundeepgoel72/myst-monitor?label=version)](https://github.com/sundeepgoel72/myst-monitor/tags)
[![Tests](https://img.shields.io/github/actions/workflow/status/sundeepgoel72/myst-monitor/test.yml?branch=main&label=tests)](https://github.com/sundeepgoel72/myst-monitor/actions/workflows/test.yml)

WSL-first monitoring bridge for Mysterium nodes, with Docker reserved for final HP400 verification and live service deployment.

## Features

- **Local Runtime Discovery**: Probes explicitly configured local MYST runtimes from WSL
- **TequilAPI Monitoring**: Read-only monitoring of Mysterium node TequilAPI endpoints
- **Prometheus Export**: Exposes container and API metrics in Prometheus format
- **SNMP Extend**: Publishes node status via SNMP extend script
- **Web UI**: Dashboard with fleet overview, history, and settings
- **Telegram Reports**: Automated earnings and metric reports
- **SQLite History**: Persistent storage of collection snapshots
- **Multi-host Support**: Configured local runtimes plus remote TequilAPI hosts

## TequilAPI Integration

MystMon implements comprehensive read-only monitoring of Mysterium node TequilAPI endpoints:

- **Endpoint Discovery**: Automatically discovers supported endpoints via OpenAPI schema
- **Safety Policy**: Enforces read-only access and blocks sensitive operations
- **Data Redaction**: Aggressively redacts sensitive information
- **Category Support**: Collects data from health, identities, services, sessions, provider stats, payments, location, NAT, and utilities
- **Metrics Export**: Exports TequilAPI data as Prometheus metrics

See [TEQUILAPI.md](docs/TEQUILAPI.md) for detailed documentation.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/sundeepgoel72/myst-monitor.git
cd myst-monitor

# Copy and customize the configuration
cp config.example.yaml config.yaml
# Edit config.yaml as needed

# Optional: copy the local override sample for host-specific settings
cp config.local.example.yaml config.local.yaml

# Create or activate the local virtualenv on WSL
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-dev.txt

# Run a focused verification check
PYTHONPATH=/home/sundeep/projects/mystmon .venv/bin/pytest tests/test_release_validation.py -q

# Verify the package imports on WSL
.venv/bin/python -c "import mystmon.api; print('ok')"
```

## Current State

- Day-to-day development and testing is now WSL-only at `/home/sundeep/projects/mystmon`.
- Local discovery no longer uses Docker fallback. The collector probes `myst.containers[*].host` directly from WSL.
- CSV export appends into the active `collection_*` file set instead of creating a new batch on every run.
- Wallet state is stored through the main snapshot/history/export path and currently appears in `mystnodes_accounts.csv`.
- `service.timezone` now controls rendered log timestamps and the persisted/exported `generated_at` / `collected_at` values used in snapshot, SQLite history, and CSV files.
- Runtime snapshot rows are now deduplicated by host/container and enriched with portal account, identity, node name, and local-match data before history/export.

## Environment Model

- All day-to-day development, debugging, linting, and test execution should happen on the WSL checkout at `/home/sundeep/projects/mystmon`.
- Use a local virtualenv on WSL for Python work.
- Docker on HP400 is reserved for final verification:
  - `mystmon-dev` only when an explicit dev-container check is needed near the end
  - `mystmon-prod` for the live service and final deployment validation

## Docker Modes

- `docker-compose.yml` runs the image-based deployment container as `mystmon-prod`.
- `docker-compose.dev.yml` pulls the published GHCR dev image as `mystmon-dev`.
- Docker is not part of local discovery.
- Local development runs the collector directly on WSL and writes snapshot/CSV outputs there.
- HP400 `mystmon-prod` remains the final live-service verification target.
- Published image source:
  - `ghcr.io/sundeepgoel72/mystmon:dev` from pushes to `main`
  - `ghcr.io/sundeepgoel72/mystmon:<version>` from release tags like `v0.1`
  - versioning policy: start at `0.1` and increment by `0.01` for each minor release

Canonical configuration:
- [config.example.yaml](config.example.yaml) for the portable base config

Optional local overrides:
- [config.local.example.yaml](config.local.example.yaml) for direct MystNodes account credentials and host-specific overrides

Environment file:
- `.env` holds runtime/deploy variables and secrets such as the TequilAPI password and SSH password.
- `.env.example` is the template for that file.
- MystNodes portal credentials are no longer stored in `.env`; they live in YAML config.

Key configuration areas:

- **MYST Collection**: configured local runtime hosts, remote TequilAPI hosts, TequilAPI settings
- **MystNodes**: one or more portal accounts in `mystnodes_accounts`
- **Prometheus**: Target endpoints for additional metric collection
- **SNMP**: Target hosts and OIDs for SNMP polling
- **History**: SQLite database path and retention settings
- **Telegram**: Bot token and chat ID for notifications
- **UI**: Web interface settings and refresh intervals

## TequilAPI Setup

To enable TequilAPI monitoring:

1. Configure TequilAPI to listen on a network-accessible address:
   ```bash
   myst config set tequilapi.address 0.0.0.0
   ```

2. Set up authentication credentials:
   ```bash
   myst config set tequilapi.auth.username myst
   myst config set tequilapi.auth.password your_secure_password
   ```

3. Configure MystMon with the credentials:
   ```yaml
   myst:
     api_username: "myst"
     api_password_env: "MYSTMON_TEQUILAPI_PASSWORD"
   ```

4. Set the environment variable:
   ```bash
   export MYSTMON_TEQUILAPI_PASSWORD="your_secure_password"
   ```

## API

See [API.md](docs/API.md) for API documentation.

Key endpoints:

- `GET /api/v1/snapshot` - Latest MYST container snapshot
- `GET /metrics` - Prometheus metrics
- `GET /api/v1/history/*` - Historical data
- `POST /api/v1/collect` - Trigger immediate collection

## Testing

Run the test suite:

```bash
# Run all tests on WSL
PYTHONPATH=/home/sundeep/projects/mystmon .venv/bin/pytest

# Run focused backend tests on WSL
PYTHONPATH=/home/sundeep/projects/mystmon .venv/bin/pytest tests/test_*.py

# Run only frontend/UI tests with Playwright when needed
PYTHONPATH=/home/sundeep/projects/mystmon .venv/bin/pytest -m ui

# Run with coverage
PYTHONPATH=/home/sundeep/projects/mystmon .venv/bin/pytest --cov=mystmon --cov-report=html
```

Operational note:
- Run code and validation on WSL by default.
- Do not use Docker containers for development testing or debugging unless explicitly requested.
- Prefer a local virtualenv for test execution.
- Use HP400 Docker only for final verification passes against `mystmon-dev` or `mystmon-prod`.

Recent verified commands:

```bash
.venv/bin/python -c "import mystmon.api; print('ok')"
PYTHONPATH=/home/sundeep/projects/mystmon .venv/bin/pytest tests/test_release_validation.py -q
PYTHONPATH=/home/sundeep/projects/mystmon .venv/bin/pytest tests/test_myst_local_discovery.py tests/test_export_csv.py tests/test_scheduler.py tests/test_mystnodes_collector.py tests/test_config.py -q
```

Latest result:
- focused backend set: `24 passed`
- release validation: `1 passed, 1 skipped`
- live local collection/export on WSL created:
  - `data/collection_10_summary.csv`
  - `data/collection_10_mystnodes_accounts.csv`
  - `data/collection_10_mystnodes_portal_nodes.csv`
  - `data/collection_10_mystnodes_local_runtime_nodes.csv`
  - `data/collection_10_mystnodes_local_hosts.csv`
  - `data/latest.json`

## Documentation

- [API.md](docs/API.md) - API endpoints and data structures
- [TEQUILAPI.md](docs/TEQUILAPI.md) - TequilAPI integration details
- [CONFIG.md](docs/CONFIG.md) - Configuration guide

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Beta Feedback

For beta releases, please provide feedback in [issue #3](https://github.com/sundeepgoel72/myst-monitor/issues/3).
