# MystMon - Current Handover

Updated: 2026-06-04

## Current State

MystMon is now treated as a first-class project in the workspace and standardized for two-agent coordination under `.codex/` and `.agents/`.
The current release is `v0.73.0`, the prod container is running `localhost:5050/mystmon:0.73`, and the live service has been validated successfully.

## Known Operational Context

- Local workspace path: `./`
- Read-only MYST monitoring service
- Target host: `192.168.1.72`
- Default service URL: `http://localhost:8072`
- Main outputs: API, Prometheus metrics, latest JSON snapshot, SNMP-style text output

## Resume Guidance

- Start with `.codex/STATUS.md` and claim scope.
- Use `.codex/PROJECT_CONTEXT.md` for durable constraints.
- Use the archived source handover for older operational notes:
  `.codex/HANDOVERS/2026-06-03-pre-reorg-handover.md`
- Track release coordination in [issue #1](https://github.com/sundeepgoel72/myst-monitor/issues/1).
- If the release commit or tag still needs publishing, push `v0.73.0` and the release commit to `origin`.

## Risk Notes

- Distinguish local code validation from remote operational validation.
- Avoid leaking or overwriting environment-specific secrets in `.env` or `config.yaml`.
- HP400 may still need an explicit runtime-path migration if it previously ran from a legacy checkout path.
- Keep `config.local.yaml` out of git and use it for machine-specific overrides only.
