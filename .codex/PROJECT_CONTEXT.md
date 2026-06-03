# MystMon - Codex Project Context

## Objective

Maintain MystMon as a lightweight, read-only monitoring service for MYST nodes running on HP400 host `192.168.1.72`.

Primary responsibilities:

- collect read-only Docker and optional TequilAPI state
- publish service/API/metrics output
- preserve safe operational boundaries around MYST nodes

## Project Shape

Main code and operations areas:

- `mystmon/` for application code
- `tests/` for pytest coverage
- `ops/` for build, install, publish, and validation scripts
- `docs/` for API and handover information
- `data/` for generated outputs

Workspace location:

- local workspace path: `/mnt/ssd/projects/mystmon`

## Operational Model

Default deployment model from docs:

- install path on HP400: `/mnt/ssd/projects/mystmon`
- default service endpoint: `http://localhost:8072`
- default polling interval: 6 hours

## Durable Constraints

- Read-only monitoring only; do not unlock identities, restart MYST containers, or alter wallet state.
- Keep TequilAPI usage optional and tolerant of missing or unauthorized endpoints.
- Separate code changes from remote-host operational actions in worklogs and handovers.
- Avoid committing secrets from `.env` or environment-specific config changes.

## Coordination Model

This project is standardized for two Codex agents sharing one checkout:

- Developer:
  code changes, tests, API/config updates
- Debugger:
  remote deployment validation, Docker/runtime investigation, output verification

Canonical coordination files live in `.codex/`.
