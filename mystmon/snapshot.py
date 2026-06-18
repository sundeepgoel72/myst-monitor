from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def build_snapshot(
    nodes: list[dict[str, Any]],
    collection_counts: dict[str, int],
    mystnodes_portal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = {
        "generated_at": datetime.now(UTC).isoformat(),
        "collection_counts": collection_counts,
        "nodes": nodes,
    }
    if mystnodes_portal is not None:
        snapshot["mystnodes"] = mystnodes_portal
    return snapshot


def write_snapshot(snapshot: dict[str, Any], latest_json_path: str, snmp_extend_path: str) -> None:
    latest_path = Path(latest_json_path)
    latest_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

    snmp_path = Path(snmp_extend_path)
    snmp_path.write_text(render_snmp_extend(snapshot), encoding="utf-8")


def render_snmp_extend(snapshot: dict[str, Any]) -> str:
    lines = [
        f"generated_at={snapshot.get('generated_at', '')}",
        f"node_count={len(snapshot.get('nodes', []))}",
    ]
    mystnodes = snapshot.get("mystnodes") or {}
    if mystnodes:
        lines.extend(
            [
                f"mystnodes.authenticated={1 if mystnodes.get('authenticated') else 0}",
                f"mystnodes.endpoint_count={len(mystnodes.get('endpoints', {}))}",
            ]
        )
        
        # Handle multi-account structure
        accounts = mystnodes.get("accounts", [])
        if accounts:
            lines.append(f"mystnodes.account_count={len(accounts)}")
            for account in accounts:
                account_name = account.get("name", "unknown")
                lines.append(f"mystnodes.account.{account_name}.authenticated={1 if account.get('authenticated') else 0}")
                lines.append(f"mystnodes.account.{account_name}.endpoint_count={len(account.get('endpoints', {}))}")
        
        # Handle nodes
        nodes = mystnodes.get("nodes", [])
        lines.append(f"mystnodes.node_count={len(nodes)}")
        for node in nodes:
            prefix = sanitize_key(node.get("name", "unknown"))
            account = node.get("account", "unknown")
            lines.extend(
                [
                    f"{prefix}.container_name={node.get('container_name', '')}",
                    f"{prefix}.running={1 if node.get('running') else 0}",
                    f"{prefix}.restart_count={node.get('restart_count', 0)}",
                    f"{prefix}.uptime_seconds={node.get('uptime_seconds', 0)}",
                    f"{prefix}.log_errors={node.get('log_counts', {}).get('error_or_warning', 0)}",
                    f"{prefix}.promises={node.get('log_counts', {}).get('promise', 0)}",
                    f"{prefix}.sessions={node.get('log_counts', {}).get('session', 0)}",
                    f"{prefix}.identity_warnings={node.get('log_counts', {}).get('identity_warning', 0)}",
                    f"{prefix}.account={account}",
                ]
            )
            api = node.get("api") or {}
            if api:
                lines.append(f"{prefix}.api_up={1 if api.get('up') else 0}")
                for metric, value in sorted(api.get("metrics", {}).items()):
                    lines.append(f"{prefix}.api.{sanitize_key(metric)}={value}")
                for endpoint, endpoint_data in sorted(api.get("endpoints", {}).items()):
                    lines.append(f"{prefix}.api_endpoint.{sanitize_key(endpoint)}={1 if endpoint_data.get('ok') else 0}")
    for node in snapshot.get("nodes", []):
        prefix = sanitize_key(node.get("name", "unknown"))
        lines.extend(
            [
                f"{prefix}.container_name={node.get('container_name', '')}",
                f"{prefix}.running={1 if node.get('running') else 0}",
                f"{prefix}.restart_count={node.get('restart_count', 0)}",
                f"{prefix}.uptime_seconds={node.get('uptime_seconds', 0)}",
                f"{prefix}.log_errors={node.get('log_counts', {}).get('error_or_warning', 0)}",
                f"{prefix}.promises={node.get('log_counts', {}).get('promise', 0)}",
                f"{prefix}.sessions={node.get('log_counts', {}).get('session', 0)}",
                f"{prefix}.identity_warnings={node.get('log_counts', {}).get('identity_warning', 0)}",
            ]
        )
        api = node.get("api") or {}
        if api:
            lines.append(f"{prefix}.api_up={1 if api.get('up') else 0}")
            for metric, value in sorted(api.get("metrics", {}).items()):
                lines.append(f"{prefix}.api.{sanitize_key(metric)}={value}")
            for endpoint, endpoint_data in sorted(api.get("endpoints", {}).items()):
                lines.append(f"{prefix}.api_endpoint.{sanitize_key(endpoint)}={1 if endpoint_data.get('ok') else 0}")
    return "\n".join(lines) + "\n"


def sanitize_key(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value).strip("_").lower()
