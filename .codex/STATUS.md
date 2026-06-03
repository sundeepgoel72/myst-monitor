# MystMon - Status

Updated: 2026-06-03

## Active Agent

- Unassigned

## Branch / Repo State

- No `.git` directory was observed in this workspace copy on 2026-06-03.
- Treat this directory as a project checkout or deployment mirror until repo state is clarified.

## Claimed Scope

- None

## Current Step

- Project standardized for shared developer/debugger coordination.
- Default runtime path updated to `/mnt/ssd/projects/mystmon`; HP400 migration may still need to be executed.

## Last Known Baseline

- Project includes API docs, tests, Docker compose files, install scripts, and handover notes.
- Operational target host remains `192.168.1.72`.

## Files / Areas In Flight

- None currently claimed

## Blockers

- Git/repo provenance for this workspace copy is not explicit.
- HP400 runtime state has not yet been checked against the new MystMon path defaults.

## Next Safe Actions

1. Claim scope before changing collectors, API, or ops scripts.
2. If HP400 previously ran MystMon from `/mnt/ssd/codex/mystmon`, execute `docs/HP400_PATH_MIGRATION.md`.
3. Record whether a task is local-code only or requires remote-host validation.
4. Update handover and worklog after any `.72` operational action.
