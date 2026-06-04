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

- local workspace path: `./`

## Operational Model

Default deployment model from docs:

- install path on HP400: repository root (`./`)
- default service endpoint: `http://localhost:8072`
- default polling interval: 6 hours
- current release: `v0.73.0`
- current prod image: `localhost:5050/mystmon:0.73`

## Durable Constraints

- Read-only monitoring only; do not unlock identities, restart MYST containers, or alter wallet state.
- Keep TequilAPI usage optional and tolerant of missing or unauthorized endpoints.
- Separate code changes from remote-host operational actions in worklogs and handovers.
- Avoid committing secrets from `.env` or environment-specific config changes.
- Prefer relative paths in docs and coordination notes.
- Create or update Git issues as a routine coordination step when it helps track work.
- Keep release metadata synchronized across `mystmon/__init__.py`, `README.md`, `docker-compose*.yml`, `.env.example`, and release docs.

## Coordination Model

This project is standardized for two Codex agents sharing one checkout:

- Developer:
  code changes, tests, API/config updates
- Debugger:
  remote deployment validation, Docker/runtime investigation, output verification

Canonical coordination files live in `.codex/`.
