# Two-Agent Coordination Plan

Use this project with two roles sharing one checkout:

- Developer:
  changes app code, tests, docs, and config defaults
- Debugger:
  validates container/runtime behavior, remote install flow, and generated outputs

Workflow:

1. Claim scope in `STATUS.md`.
2. Record whether work is local or remote-host facing.
3. Capture verification commands and results in `WORKLOG/`.
4. Leave the exact next action in `HANDOVER.md`.
