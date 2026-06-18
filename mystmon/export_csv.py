from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def write_collection_csv_exports(snapshot: dict[str, Any], data_dir: str, collection_id: int) -> list[Path]:
    output_dir = Path(data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    collected_at = str(snapshot.get("generated_at", ""))

    summary_path = output_dir / f"collection_{collection_id}_summary.csv"
    _write_rows(
        summary_path,
        ["collected_at", "field", "value"],
        ((collected_at, *row) for row in _summary_rows(snapshot)),
    )
    written.append(summary_path)

    accounts_path = output_dir / f"collection_{collection_id}_mystnodes_accounts.csv"
    _write_rows(
        accounts_path,
        [
            "collected_at",
            "account",
            "enabled",
            "authenticated",
            "base_url",
            "wallet_address",
            "node_count",
            "online_count",
            "top_os",
            "earnings_total",
            "transferred_total",
        ],
        ((collected_at, *row) for row in _account_rows(snapshot)),
    )
    written.append(accounts_path)

    portal_nodes_path = output_dir / f"collection_{collection_id}_mystnodes_portal_nodes.csv"
    _write_rows(
        portal_nodes_path,
        [
            "collected_at",
            "account",
            "id",
            "identity",
            "name",
            "local_ip",
            "external_ip",
            "online",
            "quality",
            "version",
            "os",
            "monitoring_status",
            "created_at",
            "updated_at",
            "service_types",
            "earnings_total",
        ],
        ((collected_at, *row) for row in _portal_node_rows(snapshot)),
    )
    written.append(portal_nodes_path)

    local_nodes_path = output_dir / f"collection_{collection_id}_mystnodes_local_nodes.csv"
    _write_rows(
        local_nodes_path,
        [
            "collected_at",
            "name",
            "account",
            "identity",
            "host",
            "running",
            "status",
            "restart_count",
            "uptime_seconds",
            "api_up",
            "api_status_code",
            "api_identity",
            "api_public_ip",
            "api_location_city",
            "api_location_country",
            "api_provider_quality",
            "api_sessions_1d",
            "api_sessions_7d",
            "api_nat_type",
        ],
        ((collected_at, *row) for row in _local_node_rows(snapshot)),
    )
    written.append(local_nodes_path)

    return written


def _summary_rows(snapshot: dict[str, Any]) -> list[tuple[str, str]]:
    rows = [("generated_at", str(snapshot.get("generated_at", "")))]
    counts = snapshot.get("collection_counts") or {}
    for key, value in sorted(counts.items()):
        rows.append((f"count.{key}", str(value)))
    return rows


def _account_rows(snapshot: dict[str, Any]) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    mystnodes = snapshot.get("mystnodes") or {}
    for account in mystnodes.get("accounts", []) or []:
        endpoints = account.get("endpoints") or {}
        me = _endpoint_data(endpoints, "me")
        nodes = _endpoint_data(endpoints, "nodes")
        rows.append(
            (
                str(account.get("name", "")),
                _csv_bool(account.get("enabled")),
                _csv_bool(account.get("authenticated")),
                str(account.get("base_url", "")),
                str(account.get("wallet_address", "")),
                str(_count_nodes(nodes)),
                str(_online_count(me)),
                str(_get_nested(me, ["data", "nodesInfo", "topOS"], "")),
                str(_get_nested(account, ["endpoints", "total_earnings", "data", "earningsTotal"], "")),
                str(_get_nested(account, ["endpoints", "total_transferred", "data", "transferredTotal"], "")),
            )
        )
    return rows


def _portal_node_rows(snapshot: dict[str, Any]) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    mystnodes = snapshot.get("mystnodes") or {}
    for account in mystnodes.get("accounts", []) or []:
        nodes = _endpoint_data(account.get("endpoints") or {}, "nodes")
        for node in _nodes_list(nodes):
            rows.append(
                (
                    str(account.get("name", "")),
                    str(node.get("id", "")),
                    str(node.get("identity", "")),
                    str(node.get("name", "")),
                    str(node.get("localIp", "")),
                    str(node.get("externalIp", "")),
                    _csv_bool(_get_nested(node, ["nodeStatus", "online"], False)),
                    str(_get_nested(node, ["nodeStatus", "quality"], "")),
                    str(node.get("version", "")),
                    str(node.get("os", "")),
                    str(node.get("monitoringStatus", "")),
                    str(node.get("createdAt", "")),
                    str(node.get("updatedAt", "")),
                    json.dumps(node.get("nodeStatus", {}).get("serviceTypes", []), sort_keys=True),
                    _csv_number(_earnings_total(node)),
                )
            )
    return rows


def _local_node_rows(snapshot: dict[str, Any]) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for node in snapshot.get("nodes", []) or []:
        api = node.get("api") or {}
        rows.append(
            (
                str(node.get("name", "")),
                str(node.get("account", "")),
                str(node.get("identity", "")),
                str(node.get("host", "")),
                _csv_bool(node.get("running")),
                str(node.get("status", "")),
                _csv_number(node.get("restart_count")),
                _csv_number(node.get("uptime_seconds")),
                _csv_bool(api.get("up")),
                _csv_number(api.get("status_code")),
                str(api.get("identity", "")),
                str(_get_nested(api, ["endpoints", "location", "data", "ip"], "")),
                str(_get_nested(api, ["endpoints", "location", "data", "city"], "")),
                str(_get_nested(api, ["endpoints", "location", "data", "country"], "")),
                _csv_number(_get_nested(api, ["metrics", "provider_quality"], "")),
                _csv_number(_get_nested(api, ["metrics", "provider_sessions_1d_count"], "")),
                _csv_number(_get_nested(api, ["metrics", "provider_sessions_7d_count"], "")),
                str(_get_nested(api, ["endpoints", "nat_type", "data", "type"], "")),
            )
        )
    return rows


def _write_rows(path: Path, headers: list[str], rows) -> None:
    append = path.exists()
    with path.open("a" if append else "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if not append:
            writer.writerow(headers)
        writer.writerows(rows)


def _endpoint_data(endpoints: dict[str, Any], name: str) -> dict[str, Any]:
    data = endpoints.get(name)
    if isinstance(data, dict) and "data" in data:
        return data
    return {}


def _nodes_list(endpoint_data: dict[str, Any]) -> list[dict[str, Any]]:
    data = endpoint_data.get("data") or {}
    if isinstance(data, dict):
        nodes = data.get("nodes") or []
        if isinstance(nodes, list):
            return nodes
    return []


def _count_nodes(endpoint_data: dict[str, Any]) -> int:
    return len(_nodes_list(endpoint_data))


def _online_count(endpoint_data: dict[str, Any]) -> str:
    data = endpoint_data.get("data") or {}
    if not isinstance(data, dict):
        return ""
    nodes_info = data.get("nodesInfo") or {}
    if isinstance(nodes_info, dict) and nodes_info.get("onlineCount") is not None:
        return str(nodes_info.get("onlineCount"))
    return ""


def _earnings_total(node: dict[str, Any]) -> float | str:
    earnings = node.get("earnings") or []
    if not isinstance(earnings, list):
        return ""
    total = 0.0
    for item in earnings:
        try:
            total += float(item.get("etherAmount", 0))
        except Exception:
            continue
    return total


def _get_nested(obj: Any, path: list[str], default: Any = "") -> Any:
    cur = obj
    for part in path:
        if not isinstance(cur, dict):
            return default
        if part not in cur:
            return default
        cur = cur[part]
    return cur


def _csv_bool(value: Any) -> str:
    if value is None:
        return ""
    return "1" if bool(value) else "0"


def _csv_number(value: Any) -> str:
    if value is None or value == "":
        return ""
    return str(value)
