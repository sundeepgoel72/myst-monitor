# Developer Agent Role

Own:

- collector, API, scheduler, storage, and config code changes
- pytest coverage and docs updates
- updates to `.codex/TASK.md` and `.codex/STATUS.md`

Before editing:

1. Claim scope in `.codex/STATUS.md`.
2. Create a lock file in `.agents/locks/` if you are taking a shared subsystem.

Do not:

- mix remote operational observations into code changes without documenting both separately
