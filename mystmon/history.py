from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CollectionRecord:
    id: int
    collected_at: datetime
    counts: dict[str, int]
    snapshot: dict[str, Any]


class HistoryStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS collections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collected_at TEXT NOT NULL,
                    counts_json TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_collections_collected_at
                    ON collections(collected_at);

                CREATE TABLE IF NOT EXISTS node_metrics (
                    collection_id INTEGER NOT NULL,
                    collected_at TEXT NOT NULL,
                    node_key TEXT NOT NULL,
                    node_name TEXT NOT NULL,
                    identity TEXT,
                    local_ip TEXT,
                    host TEXT,
                    container_name TEXT,
                    running REAL,
                    online REAL,
                    quality REAL,
                    earnings_total REAL,
                    uptime_seconds REAL,
                    uptime_minutes_24h REAL,
                    restart_count REAL,
                    log_error_or_warning REAL,
                    log_identity_warning REAL,
                    log_promise REAL,
                    log_session REAL,
                    local_match REAL,
                    PRIMARY KEY (collection_id, node_key),
                    FOREIGN KEY (collection_id) REFERENCES collections(id)
                );
                CREATE INDEX IF NOT EXISTS idx_node_metrics_node_time
                    ON node_metrics(node_key, collected_at);

                CREATE TABLE IF NOT EXISTS telegram_reports (
                    report_date TEXT PRIMARY KEY,
                    sent_at TEXT NOT NULL,
                    hours INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL
                );
                """
            )

    def append_snapshot(self, snapshot: dict[str, Any]) -> int:
        collected_at = _parse_time(snapshot.get("generated_at")) or datetime.now(UTC)
        counts = snapshot.get("collection_counts") or {}
        with self._connect() as db:
            cursor = db.execute(
                """
                INSERT INTO collections (collected_at, counts_json, snapshot_json)
                VALUES (?, ?, ?)
                """,
                (
                    collected_at.isoformat(),
                    json.dumps(counts, sort_keys=True),
                    json.dumps(snapshot, sort_keys=True),
                ),
            )
            collection_id = int(cursor.lastrowid)
            db.executemany(
                """
                INSERT INTO node_metrics (
                    collection_id, collected_at, node_key, node_name, identity, local_ip,
                    host, container_name, running, online, quality, earnings_total,
                    uptime_seconds, uptime_minutes_24h, restart_count,
                    log_error_or_warning, log_identity_warning, log_promise, log_session,
                    local_match
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_node_row(collection_id, collected_at, row) for row in _node_records(snapshot)],
            )
        return collection_id

    def latest_collection(self) -> dict[str, Any] | None:
        record = self._record_query("SELECT * FROM collections ORDER BY collected_at DESC, id DESC LIMIT 1")
        return _record_dict(record) if record else None

    def delta(self, hours: int = 24, now: datetime | None = None) -> dict[str, Any]:
        latest = self._record_query("SELECT * FROM collections ORDER BY collected_at DESC, id DESC LIMIT 1")
        if latest is None:
            return {"ok": False, "reason": "no_collections", "hours": hours}
        target = (now or latest.collected_at) - timedelta(hours=hours)
        prior = self._record_query(
            "SELECT * FROM collections WHERE collected_at <= ? ORDER BY collected_at DESC, id DESC LIMIT 1",
            (target.isoformat(),),
        )
        latest_nodes = self._nodes_for_collection(latest.id)
        prior_nodes = self._nodes_for_collection(prior.id) if prior else {}
        node_deltas = [_node_delta(node, prior_nodes.get(key)) for key, node in sorted(latest_nodes.items())]
        return {
            "ok": True,
            "hours": hours,
            "latest": _record_dict(latest),
            "prior": _record_dict(prior) if prior else None,
            "fleet": _fleet_delta(latest_nodes, prior_nodes if prior else None),
            "nodes": node_deltas,
        }

    def report_sent(self, report_date: str) -> bool:
        with self._connect() as db:
            row = db.execute(
                "SELECT 1 FROM telegram_reports WHERE report_date = ? AND status = 'sent'",
                (report_date,),
            ).fetchone()
        return row is not None

    def record_report(self, report_date: str, hours: int, status: str, message: str) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO telegram_reports (report_date, sent_at, hours, status, message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (report_date, datetime.now(UTC).isoformat(), hours, status, message),
            )

    def _record_query(self, query: str, params: tuple[Any, ...] = ()) -> CollectionRecord | None:
        with self._connect() as db:
            row = db.execute(query, params).fetchone()
        if row is None:
            return None
        return CollectionRecord(
            id=int(row["id"]),
            collected_at=_parse_time(row["collected_at"]) or datetime.now(UTC),
            counts=json.loads(row["counts_json"]),
            snapshot=json.loads(row["snapshot_json"]),
        )

    def _nodes_for_collection(self, collection_id: int) -> dict[str, dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM node_metrics WHERE collection_id = ? ORDER BY node_name",
                (collection_id,),
            ).fetchall()
        return {str(row["node_key"]): dict(row) for row in rows}


def _record_dict(record: CollectionRecord | None) -> dict[str, Any] | None:
    if record is None:
        return None
    return {
        "id": record.id,
        "collected_at": record.collected_at.isoformat(),
        "counts": record.counts,
    }


def _node_records(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    local_nodes = {str(node.get("name") or ""): node for node in snapshot.get("nodes", []) if isinstance(node, dict)}
    portal_nodes = _portal_nodes(snapshot)
    local_matches = ((snapshot.get("mystnodes") or {}).get("local_matches") or {})
    records: list[dict[str, Any]] = []
    used_local_names: set[str] = set()

    for portal_node in portal_nodes:
        node_id = str(portal_node.get("id") or "")
        match = local_matches.get(node_id) or {}
        local_name = str(match.get("container_name") or match.get("name") or "")
        local = local_nodes.get(local_name, {})
        if local_name:
            used_local_names.add(local_name)
        status = portal_node.get("nodeStatus") or {}
        detail = _portal_detail(snapshot, node_id)
        records.append(
            {
                "node_key": str(portal_node.get("identity") or node_id or local_name),
                "node_name": str(portal_node.get("name") or local_name or node_id),
                "identity": portal_node.get("identity"),
                "local_ip": portal_node.get("localIp"),
                "host": match.get("host") or local.get("host"),
                "container_name": local_name or local.get("name"),
                "running": _bool_number(local.get("running")),
                "online": _bool_number(status.get("online")),
                "quality": _float_or_none(status.get("quality")),
                "earnings_total": _sum_node_earnings(portal_node.get("earnings")),
                "uptime_seconds": _float_or_none(local.get("uptime_seconds")),
                "uptime_minutes_24h": _float_or_none(detail.get("uptimeMinLast24H")),
                "restart_count": _float_or_none(local.get("restart_count")),
                "log_counts": local.get("log_counts") or {},
                "local_match": 1.0 if match else 0.0,
            }
        )

    for name, local in local_nodes.items():
        if name in used_local_names:
            continue
        if portal_nodes and name.startswith("unreachable-"):
            continue
        records.append(
            {
                "node_key": name,
                "node_name": name,
                "identity": None,
                "local_ip": _first_network_ip(local),
                "host": local.get("host"),
                "container_name": local.get("name"),
                "running": _bool_number(local.get("running")),
                "online": None,
                "quality": None,
                "earnings_total": None,
                "uptime_seconds": _float_or_none(local.get("uptime_seconds")),
                "uptime_minutes_24h": None,
                "restart_count": _float_or_none(local.get("restart_count")),
                "log_counts": local.get("log_counts") or {},
                "local_match": None,
            }
        )
    return records


def _node_row(collection_id: int, collected_at: datetime, row: dict[str, Any]) -> tuple[Any, ...]:
    logs = row.get("log_counts") or {}
    return (
        collection_id,
        collected_at.isoformat(),
        row.get("node_key"),
        row.get("node_name"),
        row.get("identity"),
        row.get("local_ip"),
        row.get("host"),
        row.get("container_name"),
        row.get("running"),
        row.get("online"),
        row.get("quality"),
        row.get("earnings_total"),
        row.get("uptime_seconds"),
        row.get("uptime_minutes_24h"),
        row.get("restart_count"),
        _float_or_none(logs.get("error_or_warning")),
        _float_or_none(logs.get("identity_warning")),
        _float_or_none(logs.get("promise")),
        _float_or_none(logs.get("session")),
        row.get("local_match"),
    )


def _portal_nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    nodes_data = ((((snapshot.get("mystnodes") or {}).get("endpoints") or {}).get("nodes") or {}).get("data") or {})
    nodes = nodes_data.get("nodes") if isinstance(nodes_data, dict) else None
    return [node for node in nodes or [] if isinstance(node, dict)]


def _portal_detail(snapshot: dict[str, Any], node_id: str) -> dict[str, Any]:
    details = (((snapshot.get("mystnodes") or {}).get("node_details") or {}).get("nodes") or {})
    return (((details.get(node_id) or {}).get("detail") or {}).get("data") or {})


def _node_delta(current: dict[str, Any], prior: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "node_key": current.get("node_key"),
        "node_name": current.get("node_name"),
        "identity": current.get("identity"),
        "local_ip": current.get("local_ip"),
        "current": {
            "online": current.get("online"),
            "quality": current.get("quality"),
            "earnings_total": current.get("earnings_total"),
            "restart_count": current.get("restart_count"),
            "log_error_or_warning": current.get("log_error_or_warning"),
        },
        "delta": {
            "online": _delta(current.get("online"), prior.get("online") if prior else None),
            "quality": _delta(current.get("quality"), prior.get("quality") if prior else None),
            "earnings_total": _delta(current.get("earnings_total"), prior.get("earnings_total") if prior else None),
            "restart_count": _delta(current.get("restart_count"), prior.get("restart_count") if prior else None),
            "log_error_or_warning": _delta(
                current.get("log_error_or_warning"),
                prior.get("log_error_or_warning") if prior else None,
            ),
        },
    }


def _fleet_delta(current: dict[str, dict[str, Any]], prior: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    current_values = list(current.values())
    prior_values = list(prior.values()) if prior else []
    current_summary = _fleet_summary(current_values)
    prior_summary = _fleet_summary(prior_values) if prior else None
    return {
        "current": current_summary,
        "prior": prior_summary,
        "delta": {
            key: _delta(current_summary.get(key), prior_summary.get(key) if prior_summary else None)
            for key in current_summary
        },
    }


def _fleet_summary(nodes: list[dict[str, Any]]) -> dict[str, float | None]:
    qualities = [float(node["quality"]) for node in nodes if node.get("quality") is not None and float(node["quality"]) >= 0]
    return {
        "nodes": float(len(nodes)),
        "online": _sum_present(node.get("online") for node in nodes),
        "earnings_total": _sum_present(node.get("earnings_total") for node in nodes),
        "quality_avg": (sum(qualities) / len(qualities)) if qualities else None,
        "restart_count": _sum_present(node.get("restart_count") for node in nodes),
        "log_error_or_warning": _sum_present(node.get("log_error_or_warning") for node in nodes),
    }


def _delta(current: Any, prior: Any) -> float | str:
    current_float = _float_or_none(current)
    prior_float = _float_or_none(prior)
    if current_float is None or prior_float is None:
        return "unknown"
    return current_float - prior_float


def _sum_present(values: Any) -> float | None:
    items = [_float_or_none(value) for value in values]
    present = [value for value in items if value is not None]
    return sum(present) if present else None


def _sum_node_earnings(earnings: object) -> float | None:
    if not isinstance(earnings, list):
        return None
    total = 0.0
    for item in earnings:
        if isinstance(item, dict):
            total += _float_or_none(item.get("etherAmount")) or 0.0
    return total


def _first_network_ip(node: dict[str, Any]) -> str | None:
    networks = node.get("networks") or {}
    if not isinstance(networks, dict):
        return None
    for network in networks.values():
        if isinstance(network, dict) and network.get("ip"):
            return str(network["ip"])
    return None


def _bool_number(value: Any) -> float | None:
    if value is None:
        return None
    return 1.0 if bool(value) else 0.0


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
