# MystMon - Current Task

## Goal

Keep MystMon maintainable and handoff-safe as a monitored service project under the shared workspace standard.

## Active Priorities

1. Preserve a clear split between code changes and remote-host operational validation.
2. Keep API, collector, deployment scripts, and release metadata synchronized through handovers and worklogs.
3. Use the standardized two-agent structure for future feature work or debugging.
4. Keep the current release tracking issue updated when release coordination changes.

## Acceptance Criteria

- `.codex/` contains current context, status, and handover state.
- `.agents/` defines clear developer and debugger responsibilities.
- A future Codex session can resume MystMon work without relying on old chat context.
- Use relative paths in coordination notes instead of absolute filesystem paths.
- Treat Git issue creation and updates as a routine part of coordination when work benefits from tracking.
- Release docs reflect the current deployed tag and image name.
