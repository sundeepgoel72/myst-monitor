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
    active_collection_id = _active_collection_id(output_dir, collection_id)

    summary_path = output_dir / f"collection_{active_collection_id}_summary.csv"
    _write_rows(
        summary_path,
        ["collected_at", "field", "value"],
        ((collected_at, *row) for row in _summary_rows(snapshot)),
    )
    written.append(summary_path)

    accounts_path = output_dir / f"collection_{active_collection_id}_mystnodes_accounts.csv"
    _write_rows(
        accounts_path,
        [
            "collected_at",
            "account",
            "enabled",
            "authenticated",
            "base_url",
            "wallet_address_hint",
            "wallet_balance_ok",
            "wallet_balance_state",
            "node_count",
            "online_count",
            "top_os",
            "earnings_total",
            "transferred_total",
        ],
        ((collected_at, *row) for row in _account_rows(snapshot)),
    )
    written.append(accounts_path)

    portal_nodes_path = output_dir / f"collection_{active_collection_id}_mystnodes_portal_nodes.csv"
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

    local_runtime_nodes_path = output_dir / f"collection_{active_collection_id}_mystnodes_local_runtime_nodes.csv"
    _write_rows(
        local_runtime_nodes_path,
        [
            "collected_at",
            "host",
            "container_name",
            "portal_account",
            "portal_identity",
            "portal_node_name",
            "portal_local_ip",
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
        ((collected_at, *row) for row in _local_runtime_node_rows(snapshot)),
    )
    written.append(local_runtime_nodes_path)

    local_hosts_path = output_dir / f"collection_{active_collection_id}_mystnodes_local_hosts.csv"
    _write_rows(
        local_hosts_path,
        [
            "collected_at",
            "host",
            "matched_runtime_count",
            "matched_portal_node_count",
            "running_count",
            "accounts",
            "identities",
            "portal_node_names",
            "container_names",
        ],
        ((collected_at, *row) for row in _local_host_rows(snapshot)),
    )
    written.append(local_hosts_path)

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
                str(account.get("wallet_address_hint", "")),
                _csv_bool(_get_nested(account, ["endpoints", "wallet_balance", "ok"], None)),
                _compact_wallet_state((account.get("endpoints") or {}).get("wallet_balance")),
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


def _local_runtime_node_rows(snapshot: dict[str, Any]) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for node in _local_export_nodes(snapshot):
        api = node.get("api") or {}
        rows.append(
            (
                str(node.get("host", "")),
                str(node.get("container_name", node.get("name", ""))),
                str(node.get("portal_account", node.get("account", ""))),
                str(node.get("portal_identity", node.get("identity", ""))),
                str(node.get("portal_node_name", node.get("name", ""))),
                str(node.get("portal_local_ip", node.get("host", ""))),
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


def _local_host_rows(snapshot: dict[str, Any]) -> list[tuple[str, ...]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for node in _local_export_nodes(snapshot):
        host = str(node.get("host", ""))
        if not host:
            continue
        grouped.setdefault(host, []).append(node)

    rows: list[tuple[str, ...]] = []
    for host, nodes in sorted(grouped.items()):
        accounts = sorted({str(node.get("portal_account", "")) for node in nodes if node.get("portal_account")})
        identities = sorted({str(node.get("portal_identity", "")) for node in nodes if node.get("portal_identity")})
        portal_node_names = sorted({str(node.get("portal_node_name", "")) for node in nodes if node.get("portal_node_name")})
        container_names = sorted({str(node.get("container_name", node.get("name", ""))) for node in nodes if node.get("container_name") or node.get("name")})
        rows.append(
            (
                host,
                str(len(nodes)),
                str(len(identities)),
                str(sum(1 for node in nodes if node.get("running"))),
                json.dumps(accounts, sort_keys=True),
                json.dumps(identities, sort_keys=True),
                json.dumps(portal_node_names, sort_keys=True),
                json.dumps(container_names, sort_keys=True),
            )
        )
    return rows


def _local_export_nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    mystnodes = snapshot.get("mystnodes") or {}
    portal_nodes = {
        str(node.get("id") or ""): node
        for node in (mystnodes.get("nodes") or [])
        if isinstance(node, dict) and node.get("id")
    }
    local_matches = mystnodes.get("local_matches") or {}
    if local_matches:
        rows: list[dict[str, Any]] = []
        for node_id, match in local_matches.items():
            if not isinstance(match, dict):
                continue
            portal_node = portal_nodes.get(str(node_id), {})
            merged = dict(match)
            merged.setdefault("portal_account", portal_node.get("account", ""))
            merged.setdefault("portal_identity", portal_node.get("identity", ""))
            merged.setdefault("portal_node_name", portal_node.get("name", ""))
            merged.setdefault("portal_local_ip", portal_node.get("localIp", ""))
            merged.setdefault("host", match.get("host") or portal_node.get("localIp", ""))
            api = dict(merged.get("api") or {})
            api.setdefault("identity", portal_node.get("identity", ""))
            metrics = dict(api.get("metrics") or {})
            if metrics.get("provider_quality") in (None, ""):
                metrics["provider_quality"] = _get_nested(portal_node, ["nodeStatus", "quality"], "")
            api["metrics"] = metrics
            merged["api"] = api
            rows.append(merged)
        return rows
    return [
        node
        for node in (snapshot.get("nodes", []) or [])
        if isinstance(node, dict) and any(node.get(key) for key in ("portal_account", "portal_identity", "account", "identity"))
    ]


def _write_rows(path: Path, headers: list[str], rows) -> None:
    append = path.exists()
    row_list = list(rows)
    if append:
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            existing_rows = list(reader)
        existing_headers = existing_rows[0] if existing_rows else []
        if existing_headers != headers:
            migrated = _migrate_existing_rows(existing_rows[1:], existing_headers, headers)
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
                writer.writerows(_sanitize_rows(path, headers, migrated))
                writer.writerows(row_list)
            return
        sanitized = _sanitize_rows(path, headers, existing_rows[1:])
        if sanitized != existing_rows[1:]:
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
                writer.writerows(sanitized)
    with path.open("a" if append else "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if not append:
            writer.writerow(headers)
        writer.writerows(row_list)


def _active_collection_id(output_dir: Path, collection_id: int) -> int:
    existing_ids: list[int] = []
    for path in output_dir.glob("collection_*_summary.csv"):
        parts = path.stem.split("_")
        if len(parts) < 3:
            continue
        try:
            existing_ids.append(int(parts[1]))
        except ValueError:
            continue
    if existing_ids:
        return max(existing_ids)
    return collection_id


def _migrate_existing_rows(rows: list[list[str]], existing_headers: list[str], headers: list[str]) -> list[list[str]]:
    migrated: list[list[str]] = []
    for row in rows:
        row_map = {header: row[index] if index < len(row) else "" for index, header in enumerate(existing_headers)}
        normalized = dict(row_map)
        if "wallet_address" in row_map and "wallet_address_hint" in headers and "wallet_address_hint" not in row_map:
            normalized["wallet_address_hint"] = row_map.get("wallet_address", "")
        migrated.append([normalized.get(header, "") for header in headers])
    return migrated


def _sanitize_rows(path: Path, headers: list[str], rows: list[list[str]]) -> list[list[str]]:
    if not path.name.endswith("_mystnodes_accounts.csv"):
        return rows
    header_index = {header: index for index, header in enumerate(headers)}
    best_rows: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        normalized = list(row[: len(headers)]) + [""] * max(0, len(headers) - len(row))
        if _looks_like_misaligned_account_row(normalized, header_index):
            normalized = _repair_misaligned_account_row(normalized, header_index)
        key = (
            normalized[header_index["collected_at"]],
            normalized[header_index["account"]],
        )
        current = best_rows.get(key)
        if current is None or _row_score(normalized) >= _row_score(current):
            best_rows[key] = normalized
    return list(best_rows.values())


def _looks_like_misaligned_account_row(row: list[str], index: dict[str, int]) -> bool:
    wallet_state = row[index["wallet_balance_state"]]
    top_os = row[index["top_os"]]
    earnings = row[index["earnings_total"]]
    transferred = row[index["transferred_total"]]
    return (
        row[index["wallet_balance_ok"]] == ""
        and row[index["node_count"]] in {"0", ""}
        and wallet_state.startswith("{")
        and top_os.isdigit()
        and earnings.isdigit()
        and transferred
        and not transferred.isdigit()
    )


def _repair_misaligned_account_row(row: list[str], index: dict[str, int]) -> list[str]:
    repaired = list(row)
    repaired[index["wallet_balance_ok"]] = "0"
    repaired[index["wallet_balance_state"]] = row[index["online_count"]]
    repaired[index["node_count"]] = row[index["top_os"]]
    repaired[index["online_count"]] = row[index["earnings_total"]]
    repaired[index["top_os"]] = row[index["transferred_total"]]
    repaired[index["earnings_total"]] = ""
    repaired[index["transferred_total"]] = ""
    return repaired


def _row_score(row: list[str]) -> int:
    return sum(1 for value in row if value not in ("", None))


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


def _compact_wallet_state(endpoint: Any) -> str:
    if not isinstance(endpoint, dict):
        return ""
    if endpoint.get("ok") is False:
        return ""
    data = endpoint.get("data")
    if isinstance(data, dict):
        summary = data.get("summary")
        if summary not in (None, ""):
            return str(summary)
        for path in (
            ["balance"],
            ["availableBalance"],
            ["current", "balance"],
            ["current", "settlement", "human"],
            ["current", "settlement", "amount"],
        ):
            value = _get_nested(data, path, None)
            if value not in (None, ""):
                return str(value)
        return json.dumps(data, sort_keys=True)
    if data in (None, ""):
        return ""
    return str(data)


def _csv_bool(value: Any) -> str:
    if value is None:
        return ""
    return "1" if bool(value) else "0"


def _csv_number(value: Any) -> str:
    if value is None or value == "":
        return ""
    return str(value)
