# MystMon - Current Handover

Updated: 2026-06-03

## Current State

MystMon is now treated as a first-class project in the workspace and standardized for two-agent coordination under `.codex/` and `.agents/`.

## Known Operational Context

- Local workspace path: `/mnt/ssd/projects/mystmon`
- Read-only MYST monitoring service
- Target host: `192.168.1.72`
- Default service URL: `http://localhost:8072`
- Main outputs: API, Prometheus metrics, latest JSON snapshot, SNMP-style text output

## Resume Guidance

- Start with `.codex/STATUS.md` and claim scope.
- Use `.codex/PROJECT_CONTEXT.md` for durable constraints.
- Use the archived source handover for older operational notes:
  `.codex/HANDOVERS/2026-06-03-pre-reorg-handover.md`

## Risk Notes

- Distinguish local code validation from remote operational validation.
- Avoid leaking or overwriting environment-specific secrets in `.env` or `config.yaml`.
- HP400 may still need an explicit runtime-path migration if it previously ran from `/mnt/ssd/codex/mystmon`.
