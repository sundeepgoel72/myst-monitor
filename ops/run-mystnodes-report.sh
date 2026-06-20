#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
DATA_DIR="${MYSTMON_DATA_DIR:-/tmp/mystmon-data}"
LOG_LEVEL="${MYSTMON_LOG_LEVEL:-DEBUG}"
CONFIG_FILE="${MYSTMON_CONFIG_FILE:-config.local.yaml}"

PYTHONPATH=. MYSTMON_DATA_DIR="$DATA_DIR" MYSTMON_LOG_LEVEL="$LOG_LEVEL" "$PYTHON_BIN" - <<'PY'
import asyncio
import logging
import os

from mystmon.collectors.myst import _probe_api_async
from mystmon.collectors.mystnodes import collect_mystnodes_portal_accounts
from mystmon.config import load_config

logging.basicConfig(
    level=os.getenv("MYSTMON_LOG_LEVEL", "DEBUG").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

config = load_config(os.getenv("MYSTMON_CONFIG_FILE", "config.local.yaml"))


def _fmt(value):
    return "" if value is None else value


async def main() -> None:
    portal = await collect_mystnodes_portal_accounts(config.mystnodes_accounts, 30, [])
    portal_nodes = (portal or {}).get("nodes", [])
    local_nodes = []
    for node in portal_nodes:
        local_ip = node.get("localIp")
        identity = node.get("identity") or node.get("name") or "unknown"
        if not local_ip:
            local_nodes.append({
                "name": node.get("name", ""),
                "container_name": node.get("name", ""),
                "host": None,
                "running": None,
                "uptime_seconds": None,
                "restart_count": None,
                "warnings": ["missing localIp"],
            })
            continue
        api_probe = await _probe_api_async(
            local_ip,
            identity,
            {},
            config.myst,
            override_port=config.myst.api_default_port,
            networks=None,
        )
        local_nodes.append({
            "name": node.get("name", ""),
            "container_name": node.get("name", ""),
            "host": local_ip,
            "running": api_probe.get("up"),
            "uptime_seconds": None,
            "restart_count": None,
            "warnings": [] if api_probe.get("up") else ["tequilapi_unreachable"],
            "tequilapi": api_probe,
        })

    print("| account | authenticated | node_count | local_match_count | errors/warnings |")
    print("|---|---:|---:|---:|---|")
    for acct in (portal or {}).get("accounts", []):
        nodes = ((acct.get("endpoints") or {}).get("nodes") or {}).get("data", {}).get("nodes", [])
        local_matches = acct.get("local_matches") or {}
        err = acct.get("error") or "-"
        print(f"| `{acct.get('name', '')}` | {bool(acct.get('authenticated'))} | {len(nodes)} | {len(local_matches)} | {err} |")

    print()
    print("| display_name | container_name | identity | host/local_ip | running | uptime_seconds | quality | account |")
    print("|---|---|---|---|---:|---:|---:|---|")
    for node in (portal or {}).get("nodes", []):
        print(
            f"| `{_fmt(node.get('name', ''))}` | `{_fmt(node.get('container_name', ''))}` | `{_fmt(node.get('identity', ''))}` | "
            f"`{_fmt(node.get('host') or node.get('localIp') or '')}` | {_fmt(node.get('running'))} | {_fmt(node.get('uptime_seconds'))} | "
            f"{_fmt(node.get('quality'))} | `{_fmt(node.get('account', ''))}` |"
        )

    print()
    print("| name | local_ip | tequilapi_up | identity | version | quality | warnings |")
    print("|---|---|---:|---|---|---:|---|")
    for node in local_nodes:
        warns = ", ".join(node.get("warnings") or []) if node.get("warnings") else "-"
        tequilapi = node.get("tequilapi") or {}
        version = ((tequilapi.get("endpoints") or {}).get("healthcheck") or {}).get("data") or {}
        print(
            f"| `{_fmt(node.get('name', ''))}` | `{_fmt(node.get('host', ''))}` | {_fmt(tequilapi.get('up'))} | "
            f"`{_fmt(tequilapi.get('identity'))}` | `{_fmt(version.get('version'))}` | {_fmt((tequilapi.get('metrics') or {}).get('provider_quality'))} | {warns} |"
        )


asyncio.run(main())
PY
