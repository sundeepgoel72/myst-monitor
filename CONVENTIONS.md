# MystMon Coding Conventions

These conventions are for Codex, Aider, and other coding agents working in this repository.

## Unknown Monitoring Values

Never coerce unknown monitoring values to zero unless the source explicitly reports numeric zero.

Examples:

- `null` MystNodes portal earnings means unknown, not `0 MYST`.
- `null` portal uptime means unknown, not `0m`.
- `null` portal quality means unknown, not quality `0`.
- `null` portal `online` means portal status is unknown. The UI may use local Docker `running` as a health label fallback (`Running` or `Stopped`), but it must not report portal `Online` or `Offline` from that fallback.

Docker `running` is local health state only. It does not imply portal `online`, earnings, quality, or portal uptime.

Deploy flow:

- Start `mystmon-registry` before build/test/deploy work if the workflow needs the auxiliary registry.
- Stop `mystmon-registry` after the deploy/test step completes.

## Aider Run

- Read `CONVENTIONS.md` and `.codex/HANDOVER.md` before making changes.
- Keep changes scoped to the current issue and avoid rewriting unrelated history.
- Run the smallest relevant checks first, then full validation before reporting done.
- Prefer the repo's deploy scripts and release notes over ad hoc container commands.
- Use local host execution for validation and debugging unless the user explicitly asks for Docker/container execution.
- For tests, prefer a local virtualenv or local host Python. Do not use a container test harness unless explicitly requested.
