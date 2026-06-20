# MystMon

[![License](https://img.shields.io/github/license/sundeepgoel72/myst-monitor)](LICENSE)
[![Version](https://img.shields.io/github/v/tag/sundeepgoel72/myst-monitor?label=version)](https://github.com/sundeepgoel72/myst-monitor/tags)
[![Tests](https://img.shields.io/github/actions/workflow/status/sundeepgoel72/myst-monitor/test.yml?branch=main&label=tests)](https://github.com/sundeepgoel72/myst-monitor/actions/workflows/test.yml)

MystMon is a read-only monitoring service for MYST nodes. It collects runtime and portal state, writes snapshots and CSV exports, exposes an HTTP API and Prometheus metrics, and supports a lightweight web UI for inspection.

## Core Capabilities

- Monitors local and remote MYST runtimes through read-only TequilAPI calls
- Supports multiple MystNodes portal accounts in one deployment
- Derives local runtime coverage from live portal node `localIp` data instead of relying only on static host lists
- Stores snapshots and SQLite history with local-time timestamps driven by `service.timezone`
- Exports separate CSV views for accounts, portal nodes, local runtimes, and local hosts
- Exposes HTTP API, Prometheus metrics, and an optional inspection UI

## How To Deploy And Run

Use Docker for normal operation.

For a normal install, pull a specific released version. The current example version is `0.11`:

```bash
docker pull ghcr.io/sundeepgoel72/mystmon:0.11
```

If you explicitly want the latest build from `main`, use:

```bash
docker pull ghcr.io/sundeepgoel72/mystmon:dev
```

After pulling the image, create these local files:

```bash
cp config.example.yaml config.yaml
mkdir -p data
```

Use only one runtime config file: `config.yaml`.
If an older `config.local.yaml` is still present from a previous setup, remove it and consolidate any needed settings into `config.yaml`.
`.env` is not part of the normal runtime flow.

Configuration file:
- `config.yaml`
  - your active runtime config
  - copied from `config.example.yaml`
  - use this for timezone, output paths, MystNodes portal accounts, and optional local runtime discovery settings

Key configuration areas to review before first run:
- `service`
  - polling interval, data paths, timezone
- `mystnodes_accounts`
  - one or more MystNodes portal accounts
- `outputs`
  - latest snapshot, SNMP text, and CSV export paths
- `history`
  - SQLite history database path

Typical config flow:
- set `service.timezone` to your operational timezone
- add your MystNodes portal accounts under `mystnodes_accounts`

Example snippet:

```yaml
service:
  timezone: Asia/Kolkata

mystnodes_accounts:
  - account: your-myst-email@example.com
    enabled: true
    password: change-me
    wallet_address: 0x1234567890abcdef1234567890abcdef12345678
```

Create a lightweight `docker-compose.yml` in the same directory:

```yaml
services:
  mystmon:
    image: ghcr.io/sundeepgoel72/mystmon:0.11
    container_name: mystmon
    restart: unless-stopped
    ports:
      - "8072:8072"
    environment:
      MYSTMON_CONFIG: /app/config.yaml
      MYSTMON_HOST: 0.0.0.0
      MYSTMON_PORT: 8072
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./data:/data/mystmon
    healthcheck:
      test:
        - CMD-SHELL
        - python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8072/health', timeout=3).read()"
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
```

Start the service:

```bash
docker compose up -d
```

The password environment variables are not part of the simple `0.11` example because they are only needed when your specific configuration actually uses them.

The root-level `.env` file from older deployment flows is obsolete and should not be used for a normal `0.11` install.

Health check:

```bash
curl http://YOUR_HOST_OR_IP:8072/health
```

Container health state:

```bash
docker inspect -f '{{.State.Health.Status}}' mystmon
```

With the default relative-path config, outputs are written under `data/` relative to the runtime working directory. In the compose example, that is backed by your mounted `./data` directory.

## Development And Validation

For source-based setup, testing, and developer workflow, see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Deployment Notes

- Normal and production-style deployments should use a specific version tag such as `ghcr.io/sundeepgoel72/mystmon:0.11`.
- `ghcr.io/sundeepgoel72/mystmon:dev` tracks the latest `main` build and is better suited for preview or validation environments.
- Both shipped compose samples include a container healthcheck against `/health`.
- Versioning starts at `0.1` and increments by `0.01` for each minor release.
- If the package page shows stale metadata, check the latest `Publish Docker Image` workflow run first. GHCR metadata updates only after a successful image push.

## Documentation

- [docs/API.md](docs/API.md) - API surface and history endpoints
- [docs/CONVENTIONS.md](docs/CONVENTIONS.md) - contributor and in-file review comment conventions
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) - source setup and developer validation
- [docs/TEQUILAPI.md](docs/TEQUILAPI.md) - TequilAPI collection details
- [docs/DESIGN.md](docs/DESIGN.md) - architecture and maintainer design notes

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
