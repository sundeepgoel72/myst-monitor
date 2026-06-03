# MystMon - Archived Handover

Archived during Codex coordination reorganization on 2026-06-03.

This file preserves the operational notes that previously lived in `docs/HANDOVER.md`.

## Preserved Summary

- Runs on `192.168.1.72` from `/mnt/ssd/projects/mystmon`
- Performs read-only Docker inspection and optional TequilAPI collection
- Writes JSON and SNMP-style outputs under `/data/mystmon/`
- Uses a 6-hour default polling interval
- Includes install, cron fallback, and validation commands in `ops/`
