# MystMon - Current Task

## Goal

Keep MystMon maintainable and handoff-safe as a monitored service project under the shared workspace standard.

## Active Priorities

1. Preserve a clear split between code changes and remote-host operational validation.
2. Keep API, collector, and deployment scripts synchronized through handovers and worklogs.
3. Use the standardized two-agent structure for future feature work or debugging.

## Acceptance Criteria

- `.codex/` contains current context, status, and handover state.
- `.agents/` defines clear developer and debugger responsibilities.
- A future Codex session can resume MystMon work without relying on old chat context.
