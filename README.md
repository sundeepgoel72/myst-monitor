# MystMon

[![License](https://img.shields.io/github/license/sundeepgoel72/myst-monitor)](LICENSE)
[![Release](https://img.shields.io/github/v/release/sundeepgoel72/myst-monitor)](https://github.com/sundeepgoel72/myst-monitor/releases)
[![Tests](https://img.shields.io/github/actions/workflow/status/sundeepgoel72/myst-monitor/test.yml?branch=main&label=tests)](https://github.com/sundeepgoel72/myst-monitor/actions/workflows/test.yml)

Dockerized Prometheus and SNMP monitoring bridge for Mysterium nodes.

## Features

- **Docker Integration**: Auto-discovers local and remote MYST containers
- **TequilAPI Monitoring**: Read-only monitoring of Mysterium node TequilAPI endpoints
- **Prometheus Export**: Exposes container and API metrics in Prometheus format
- **SNMP Extend**: Publishes node status via SNMP extend script
- **Web UI**: Dashboard with fleet overview, history, and settings
- **Telegram Reports**: Automated earnings and metric reports
- **SQLite History**: Persistent storage of collection snapshots
- **Multi-host Support**: SSH-based inventory of remote Docker hosts

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

# Start the service
docker compose up -d

# Access the web UI
open http://localhost:8072/ui
```

## Configuration

Canonical configuration:
- [config.example.yaml](config.example.yaml) for the portable base config

Optional local overrides:
- [config.local.example.yaml](config.local.example.yaml) for direct MystNodes account credentials and host-specific overrides

Environment file:
- `.env` holds runtime/deploy variables and secrets such as the TequilAPI password and SSH password.
- `.env.example` is the template for that file.
- MystNodes portal credentials are no longer stored in `.env`; they live in YAML config.

Key configuration areas:

- **MYST Collection**: Docker socket, container patterns, TequilAPI settings
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
# Run all tests
pytest

# Run only backend tests
pytest tests/test_*.py

# Run only frontend/UI tests with Playwright
pytest -m ui

# Run with coverage
pytest --cov=mystmon --cov-report=html
```

Operational note:
- Run code and validation locally on the host by default.
- Do not use Docker containers for testing or debugging unless explicitly requested.
- Prefer a local virtualenv for test execution when possible.

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
