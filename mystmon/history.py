"""History storage for MystMon snapshots.

Provides persistent storage of collection snapshots using SQLite database.
Stores node data, collection counts, and portal information for historical
analysis and reporting.

The history store maintains a time-series of collection snapshots, allowing
for trend analysis, delta calculations, and historical reporting.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectionRecord:
    """A record of a collection snapshot.
    
    Represents a single point-in-time snapshot of the entire MystMon state
    including node data, collection counts, and portal information.
    """
    id: int
    collected_at: datetime
    counts: dict[str, int]
    snapshot: dict[str, Any]


class HistoryStore:
    """SQLite-based storage for collection history.
    
    Provides persistent storage of collection snapshots with efficient
    querying capabilities for historical analysis and reporting.
    """
    
    def __init__(self, db_path: str) -> None:
        """Initialize the history store.
        
        Creates the database file and initializes the schema if needed.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        LOGGER.info("History database path: %s", self.db_path)

    def _connect(self) -> sqlite3.Connection:
        """Get a database connection.
        
        Provides a connection to the SQLite database with row factory setup.
        
        Returns:
            SQLite database connection
        """
        connection = None
        try:
            connection = sqlite3.connect(self.db_path)
            connection.row_factory = sqlite3.Row
            return connection
        except Exception:
            if connection:
                connection.close()
            raise

    def append_snapshot(self, snapshot: dict[str, Any]) -> int:
        """Append a snapshot to the history.
        
        Stores a complete snapshot of the current MystMon state including
        node data, collection counts, and portal information.
        
        Args:
            snapshot: The snapshot data to store
            
        Returns:
            ID of the inserted record
        """
        LOGGER.debug("Appending snapshot to history")
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
                    local_match, api_enabled, api_up, api_auth, api_schema_available,
                    api_last_check, api_base_url, api_status_code, api_identity,
                    api_public_ip, api_location_city, api_location_country, api_location_isp,
                    api_location_asn, api_nat_type, api_services_count, api_services_running,
                    api_service_types, api_sessions_active, api_sessions_1d, api_sessions_7d,
                    api_provider_quality, api_provider_transferred_data, api_payments_balance,
                    api_settlements_count, api_config_present
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_node_row(collection_id, collected_at, row) for row in _node_records(snapshot)],
            )
        return collection_id

    def latest_collection(self) -> dict[str, Any] | None:
        """Get the latest collection record.
        
        Returns:
            Latest collection record or None if no collections exist
        """
        LOGGER.debug("Fetching latest collection")
        record = self._record_query("SELECT * FROM collections ORDER BY collected_at DESC, id DESC LIMIT 1")
        return _record_dict(record) if record else None

    def overall(self, limit: int = 100) -> dict[str, Any]:
        """Get overall history with fleet summaries.
        
        Args:
            limit: Maximum number of collections to return
            
        Returns:
            Dictionary with overall history data
        """
        LOGGER.debug("Fetching overall history with limit=%d", limit)
        rows = self._collection_rows(limit)
        return {
            "ok": True,
            "count": len(rows),
            "collections": [
                {
                    **_record_dict(record),
                    "fleet": _fleet_summary(list(self._nodes_for_collection(record.id).values())),
                }
                for record in rows
            ],
        }

    def nodes(self, latest_only: bool = True, limit: int = 100) -> dict[str, Any]:
        """Get node data from history.
        
        Args:
            latest_only: Whether to return only latest nodes
            limit: Maximum number of nodes to return
            
        Returns:
            Dictionary with node data
        """
        LOGGER.debug("Fetching nodes with latest_only=%s, limit=%d", latest_only, limit)
        if latest_only:
            latest = self._record_query("SELECT * FROM collections ORDER BY collected_at DESC, id DESC LIMIT 1")
            if latest is None:
                return {"ok": True, "count": 0, "nodes": []}
            nodes = list(self._nodes_for_collection(latest.id).values())
            return {
                "ok": True,
                "collection": _record_dict(latest),
                "count": len(nodes),
                "nodes": [_public_node(row) for row in nodes],
            }
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT *
                FROM node_metrics
                ORDER BY collected_at DESC, node_name
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return {"ok": True, "count": len(rows), "nodes": [_public_node(dict(row)) for row in rows]}

    def node(self, node: str, limit: int = 100) -> dict[str, Any]:
        """Get history for a specific node.
        
        Args:
            node: Node identifier to search for
            limit: Maximum number of history records to return
            
        Returns:
            Dictionary with node history data
        """
        LOGGER.debug("Fetching node history for node=%s, limit=%d", node, limit)
        pattern = f"%{node}%"
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT *
                FROM node_metrics
                WHERE node_key = ?
                   OR identity = ?
                   OR node_name = ?
                   OR node_name LIKE ?
                   OR container_name = ?
                ORDER BY collected_at DESC
                LIMIT ?
                """,
                (node, node, node, pattern, node, limit),
            ).fetchall()
        public_rows = [_public_node(dict(row)) for row in rows]
        return {
            "ok": True,
            "node": node,
            "count": len(public_rows),
            "history": public_rows,
        }

    def delta(self, hours: int = 24, now: datetime | None = None) -> dict[str, Any]:
        """Get delta between current and prior collections.
        
        Args:
            hours: Hours to look back for comparison
            now: Reference time for comparison
            
        Returns:
            Dictionary with delta data
        """
        LOGGER.debug("Fetching delta for hours=%d", hours)
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
        """Check if a report was sent for a specific date.
        
        Args:
            report_date: Date to check for report
            
        Returns:
            True if report was sent, False otherwise
        """
        with self._connect() as db:
            row = db.execute(
                "SELECT 1 FROM telegram_reports WHERE report_date = ? AND status = 'sent'",
                (report_date,),
            ).fetchone()
        return row is not None

    def record_report(self, report_date: str, hours: int, status: str, message: str) -> None:
        """Record a telegram report in the database.
        
        Args:
            report_date: Date of the report
            hours: Hours covered by the report
            status: Status of the report
            message: Message content
        """
        LOGGER.info("Recording telegram report for date=%s status=%s", report_date, status)
        with self._connect() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO telegram_reports (report_date, sent_at, hours, status, message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (report_date, datetime.now(UTC).isoformat(), hours, status, message),
            )

    def _record_query(self, query: str, params: tuple[Any, ...] = ()) -> CollectionRecord | None:
        """Execute a record query and return a CollectionRecord.
        
        Args:
            query: SQL query to execute
            params: Query parameters
            
        Returns:
            CollectionRecord or None
        """
        if not query.strip().upper().startswith(('SELECT', 'WITH')):
            raise ValueError("Only SELECT queries are allowed")
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
        """Get nodes for a specific collection.
        
        Args:
            collection_id: ID of the collection
            
        Returns:
            Dictionary of nodes keyed by node key
        """
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM node_metrics WHERE collection_id = ? ORDER BY node_name",
                (collection_id,),
            ).fetchall()
        return {str(row["node_key"]): dict(row) for row in rows}

    def _collection_rows(self, limit: int) -> list[CollectionRecord]:
        """Get collection rows from the database.
        
        Args:
            limit: Maximum number of rows to return
            
        Returns:
            List of CollectionRecord objects
        """
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM collections ORDER BY collected_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            CollectionRecord(
                id=int(row["id"]),
                collected_at=_parse_time(row["collected_at"]) or datetime.now(UTC),
                counts=json.loads(row["counts_json"]),
                snapshot=json.loads(row["snapshot_json"]),
            )
            for row in rows
        ]


def _record_dict(record: CollectionRecord | None) -> dict[str, Any] | None:
    """Convert a CollectionRecord to a dictionary.
    
    Args:
        record: CollectionRecord to convert
        
    Returns:
        Dictionary representation or None
    """
    if record is None:
        return None
    return {
        "id": record.id,
        "collected_at": record.collected_at.isoformat(),
        "counts": record.counts,
    }


def _public_node(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a node row to a public node dictionary.
    
    Args:
        row: Node row data
        
    Returns:
        Public node dictionary
    """
    quality = row.get("quality")
    earnings_total = row.get("earnings_total")
    uptime_minutes_24h = row.get("uptime_minutes_24h")
    uptime_seconds = row.get("uptime_seconds")
    return {
        "collection_id": row.get("collection_id"),
        "collected_at": row.get("collected_at"),
        "node_key": row.get("node_key"),
        "node_name": row.get("node_name"),
        "identity": row.get("identity"),
        "local_ip": row.get("local_ip"),
        "host": row.get("host"),
        "container_name": row.get("container_name"),
        "running": row.get("running"),
        "online": row.get("online"),
        "quality": quality,
        "quality_known": quality is not None,
        "earnings_total": earnings_total,
        "earnings_known": earnings_total is not None,
        "uptime_seconds": uptime_seconds,
        "uptime_known": uptime_seconds is not None or uptime_minutes_24h is not None,
        "uptime_minutes_24h": uptime_minutes_24h,
        "restart_count": row.get("restart_count"),
        "log_error_or_warning": row.get("log_error_or_warning"),
        "log_identity_warning": row.get("log_identity_warning"),
        "log_promise": row.get("log_promise"),
        "log_session": row.get("log_session"),
        "local_match": row.get("local_match"),
        "api_enabled": row.get("api_enabled"),
        "api_up": row.get("api_up"),
        "api_auth": row.get("api_auth"),
        "api_schema_available": row.get("api_schema_available"),
        "api_last_check": row.get("api_last_check"),
        "api_base_url": row.get("api_base_url"),
        "api_status_code": row.get("api_status_code"),
        "api_identity": row.get("api_identity"),
        "api_public_ip": row.get("api_public_ip"),
        "api_location_city": row.get("api_location_city"),
        "api_location_country": row.get("api_location_country"),
        "api_location_isp": row.get("api_location_isp"),
        "api_location_asn": row.get("api_location_asn"),
        "api_nat_type": row.get("api_nat_type"),
        "api_services_count": row.get("api_services_count"),
        "api_services_running": row.get("api_services_running"),
        "api_service_types": row.get("api_service_types"),
        "api_sessions_active": row.get("api_sessions_active"),
        "api_sessions_1d": row.get("api_sessions_1d"),
        "api_sessions_7d": row.get("api_sessions_7d"),
        "api_provider_quality": row.get("api_provider_quality"),
        "api_provider_transferred_data": row.get("api_provider_transferred_data"),
        "api_payments_balance": row.get("api_payments_balance"),
        "api_settlements_count": row.get("api_settlements_count"),
        "api_config_present": row.get("api_config_present"),
    }


def _node_records(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract node records from a snapshot.
    
    Args:
        snapshot: Snapshot data
        
    Returns:
        List of node record dictionaries
    """
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
        api = local.get("api") or {}
        management = api.get("management") or {}
        location = _first_location_payload(management.get("location"))
        nat = _first_nat_payload(management.get("nat"))
        services = _first_category_payload(management.get("services"), ("services",)) or {}
        sessions_bucket = management.get("sessions") or {}
        sessions = _first_category_payload(sessions_bucket, ("session_stats_aggregated", "sessions_stats_daily", "sessions")) or {}
        session_details = _first_category_payload(sessions_bucket, ("sessions",)) or {}
        provider = _first_category_payload(management.get("provider"), ("provider_quality", "provider_activity_stats", "provider_service_earnings", "provider_sessions_1d", "provider_sessions_7d")) or {}
        payments = _first_category_payload(management.get("payments"), ("transactor_fees_v2", "transactor_fees")) or {}
        settlements = management.get("settlements") or {}
        config_data = management.get("config") or {}
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
                "api_enabled": _bool_number(api.get("enabled")),
                "api_up": _bool_number(api.get("up")),
                "api_auth": _bool_number(api.get("auth")),
                "api_schema_available": _bool_number(api.get("schema_available")),
                "api_last_check": api.get("last_check"),
                "api_base_url": api.get("base_url"),
                "api_status_code": api.get("status_code"),
                "api_identity": api.get("identity"),
                "api_public_ip": _first_string_value(location or {}, ("public_ip", "publicIp", "ip", "address")),
                "api_location_city": _first_string_value(location or {}, ("city", "town")),
                "api_location_country": _first_string_value(location or {}, ("country", "country_code", "countryCode")),
                "api_location_isp": _first_string_value(location or {}, ("isp", "provider", "network")),
                "api_location_asn": _first_string_value(location or {}, ("asn", "asn_name", "asnName")),
                "api_nat_type": _first_string_value(nat or {}, ("type", "nat_type", "natType")) if isinstance(nat, dict) else (str(nat) if nat else None),
                "api_services_count": _float_or_none(services.get("count")),
                "api_services_running": _float_or_none(services.get("running_count")),
                "api_service_types": _json_or_none(services.get("types")),
                "api_sessions_active": _session_active_value(session_details) or _session_active_value(sessions),
                "api_sessions_1d": _extract_time_bucket(sessions, "1d") or _provider_range_value(provider, "1d"),
                "api_sessions_7d": _extract_time_bucket(sessions, "7d") or _provider_range_value(provider, "7d"),
                "api_provider_quality": _float_or_none(provider.get("quality")),
                "api_provider_transferred_data": _first_numeric(provider.get("transferred_data")),
                "api_payments_balance": _first_numeric(payments.get("balance")),
                "api_settlements_count": _collection_count(settlements),
                "api_config_present": 1.0 if bool(config_data) else 0.0,
            }
        )

    for name, local in local_nodes.items():
        if name in used_local_names:
            continue
        if portal_nodes and name.startswith("unreachable-"):
            continue
        api = local.get("api") or {}
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
                "api_enabled": _bool_number(api.get("enabled")) if api else None,
                "api_up": _bool_number(api.get("up")) if api else None,
                "api_auth": _bool_number(api.get("auth")) if api else None,
                "api_schema_available": _bool_number(api.get("schema_available")) if api else None,
                "api_last_check": api.get("last_check") if api else None,
                "api_base_url": api.get("base_url") if api else None,
                "api_status_code": api.get("status_code") if api else None,
                "api_identity": api.get("identity") if api else None,
                "api_public_ip": None,
                "api_location_city": None,
                "api_location_country": None,
                "api_location_isp": None,
                "api_location_asn": None,
                "api_nat_type": None,
                "api_services_count": None,
                "api_services_running": None,
                "api_service_types": None,
                "api_sessions_active": None,
                "api_sessions_1d": None,
                "api_sessions_7d": None,
                "api_provider_quality": None,
                "api_provider_transferred_data": None,
                "api_payments_balance": None,
                "api_settlements_count": None,
                "api_config_present": None,
            }
        )
    return records


def _node_row(collection_id: int, collected_at: datetime, row: dict[str, Any]) -> tuple[Any, ...]:
    """Convert a node record to a database row.
    
    Args:
        collection_id: Collection ID
        collected_at: Collection timestamp
        row: Node record
        
    Returns:
        Tuple representing database row
    """
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
        row.get("api_enabled"),
        row.get("api_up"),
        row.get("api_auth"),
        row.get("api_schema_available"),
        row.get("api_last_check"),
        row.get("api_base_url"),
        row.get("api_status_code"),
        row.get("api_identity"),
        row.get("api_public_ip"),
        row.get("api_location_city"),
        row.get("api_location_country"),
        row.get("api_location_isp"),
        row.get("api_location_asn"),
        row.get("api_nat_type"),
        row.get("api_services_count"),
        row.get("api_services_running"),
        row.get("api_service_types"),
        row.get("api_sessions_active"),
        row.get("api_sessions_1d"),
        row.get("api_sessions_7d"),
        row.get("api_provider_quality"),
        row.get("api_provider_transferred_data"),
        row.get("api_payments_balance"),
        row.get("api_settlements_count"),
        row.get("api_config_present"),
    )


def _first_numeric(value: Any) -> float | None:
    """Extract the first numeric value from data.
    
    Args:
        value: Data to extract from
        
    Returns:
        First numeric value or None
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for item in value.values():
            numeric = _first_numeric(item)
            if numeric is not None:
                return numeric
    if isinstance(value, list):
        for item in value:
            numeric = _first_numeric(item)
            if numeric is not None:
                return numeric
    return None


def _json_or_none(value: Any) -> str | None:
    """Convert a value to JSON or return None.
    
    Args:
        value: Value to convert
        
    Returns:
        JSON string or None
    """
    if value is None:
        return None
    try:
        return json.dumps(value, sort_keys=True)
    except TypeError:
        return json.dumps(str(value))


def _first_string_value(data: dict[str, Any] | None, keys: tuple[str, ...]) -> str | None:
    """Extract the first string value for specified keys.
    
    Args:
        data: Data dictionary
        keys: Keys to look for
        
    Returns:
        First string value or None
    """
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            return str(value)
    return None


def _collection_count(value: Any) -> float | None:
    """Get a count from collection data.
    
    Args:
        value: Data to count
        
    Returns:
        Count as float or None
    """
    if isinstance(value, dict):
        for key in ("count", "total", "length", "size"):
            numeric = _first_numeric(value.get(key))
            if numeric is not None:
                return numeric
        return float(len(value))
    if isinstance(value, list):
        return float(len(value))
    numeric = _first_numeric(value)
    return numeric


def _extract_time_bucket(sessions: dict[str, Any], bucket: str) -> float | None:
    """Extract a value from a time bucket.
    
    Args:
        sessions: Sessions data
        bucket: Time bucket name
        
    Returns:
        Bucket value or None
    """
    if not isinstance(sessions, dict):
        return None
    for key in (bucket, f"stats_{bucket}", f"stats{bucket}", f"{bucket}_count", f"{bucket}Count", "daily"):
        numeric = _first_numeric(sessions.get(key))
        if numeric is not None:
            return numeric
    return None


def _first_location_payload(value: Any) -> dict[str, Any] | None:
    """Extract the first location payload.
    
    Args:
        value: Data to extract from
        
    Returns:
        Location data or None
    """
    if isinstance(value, dict):
        for key in ("location", "connection_location", "connection_proxy_location"):
            nested = value.get(key)
            if isinstance(nested, dict):
                return nested
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return _first_location_payload(item)
    return None


def _first_nat_payload(value: Any) -> dict[str, Any] | None:
    """Extract the first NAT payload.
    
    Args:
        value: Data to extract from
        
    Returns:
        NAT data or None
    """
    if isinstance(value, dict):
        for key in ("nat_type", "natType", "type"):
            nested = value.get(key)
            if isinstance(nested, dict):
                return nested
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return _first_nat_payload(item)
    return None


def _first_category_payload(value: Any, preferred_keys: tuple[str, ...]) -> dict[str, Any] | None:
    """Extract the first payload from a category.
    
    Args:
        value: Data to extract from
        preferred_keys: Preferred keys to look for
        
    Returns:
        Payload data or None
    """
    if isinstance(value, dict):
        for key in preferred_keys:
            nested = value.get(key)
            if isinstance(nested, dict):
                return nested
        for nested in value.values():
            if isinstance(nested, dict):
                return nested
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return _first_category_payload(item, preferred_keys)
    return None


def _session_active_value(sessions: Any) -> float | None:
    """Extract active session count.
    
    Args:
        sessions: Sessions data
        
    Returns:
        Active session count or None
    """
    if not isinstance(sessions, dict):
        return None
    for key in ("active", "count"):
        numeric = _first_numeric(sessions.get(key))
        if numeric is not None:
            return numeric
    daily = sessions.get("daily")
    if isinstance(daily, dict):
        for key in ("count", "active", "sessions"):
            numeric = _first_numeric(daily.get(key))
            if numeric is not None:
                return numeric
    return None


def _provider_range_value(provider: Any, bucket: str) -> float | None:
    """Extract a range value from provider data.
    
    Args:
        provider: Provider data
        bucket: Time bucket name
        
    Returns:
        Range value or None
    """
    if not isinstance(provider, dict):
        return None
    for key in ("sessions", "activity", "transferred_data", "service_earnings"):
        value = provider.get(key)
        if isinstance(value, dict):
            numeric = _extract_time_bucket(value, bucket)
            if numeric is not None:
                return numeric
    return None


def _portal_nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract portal nodes from a snapshot.
    
    Args:
        snapshot: Snapshot data
        
    Returns:
        List of portal nodes
    """
    mystnodes = snapshot.get("mystnodes") or {}
    endpoints = mystnodes.get("endpoints") or {}
    nodes_data = endpoints.get("nodes") or {}
    nodes = nodes_data.get("data") or {}
    return [node for node in nodes.get("nodes", []) if isinstance(node, dict)] if isinstance(nodes, dict) else []


def _portal_detail(snapshot: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Extract portal detail for a node.
    
    Args:
        snapshot: Snapshot data
        node_id: Node ID
        
    Returns:
        Portal detail data
    """
    mystnodes = snapshot.get("mystnodes") or {}
    node_details = mystnodes.get("node_details") or {}
    nodes = node_details.get("nodes") or {}
    node_data = nodes.get(node_id) or {}
    detail = node_data.get("detail") or {}
    return detail.get("data") or {}


def _node_delta(current: dict[str, Any], prior: dict[str, Any] | None) -> dict[str, Any]:
    """Calculate delta between current and prior node data.
    
    Args:
        current: Current node data
        prior: Prior node data
        
    Returns:
        Delta data
    """
    return {
        "node_key": current.get("node_key"),
        "node_name": current.get("node_name"),
        "identity": current.get("identity"),
        "local_ip": current.get("local_ip"),
        "current": {
            "running": current.get("running"),
            "online": current.get("online"),
            "quality": current.get("quality"),
            "earnings_total": current.get("earnings_total"),
            "restart_count": current.get("restart_count"),
            "log_error_or_warning": current.get("log_error_or_warning"),
        },
        "delta": {
            "running": _delta(current.get("running"), prior.get("running") if prior else None),
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
    """Calculate delta between current and prior fleet data.
    
    Args:
        current: Current fleet data
        prior: Prior fleet data
        
    Returns:
        Fleet delta data
    """
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
    """Create a summary of fleet data.
    
    Args:
        nodes: List of node data
        
    Returns:
        Fleet summary
    """
    if not nodes:
        return {
            "nodes": 0.0,
            "running": 0.0,
            "online": None,
            "earnings_total": None,
            "quality_avg": None,
            "restart_count": 0.0,
            "log_error_or_warning": 0.0,
        }

    total_nodes = float(len(nodes))
    running_nodes = _sum_present(node.get("running") for node in nodes) or 0.0
    online_nodes = _sum_present(node.get("online") for node in nodes)
    qualities = [
        float(node["quality"])
        for node in nodes
        if node.get("quality") is not None and float(node["quality"]) >= 0
    ]

    return {
        "nodes": total_nodes,
        "running": running_nodes,
        "online": online_nodes,
        "earnings_total": _sum_present(node.get("earnings_total") for node in nodes),
        "quality_avg": (sum(qualities) / len(qualities)) if qualities else None,
        "restart_count": _sum_present(node.get("restart_count") for node in nodes) or 0.0,
        "log_error_or_warning": _sum_present(node.get("log_error_or_warning") for node in nodes) or 0.0,
    }


def _delta(current: Any, prior: Any) -> float | str:
    """Calculate delta between current and prior values.
    
    Args:
        current: Current value
        prior: Prior value
        
    Returns:
        Delta value or "unknown"
    """
    current_float = _float_or_none(current)
    prior_float = _float_or_none(prior)
    if current_float is None or prior_float is None:
        return "unknown"
    return current_float - prior_float


def _sum_present(values: Any) -> float | None:
    """Sum present values.
    
    Args:
        values: Values to sum
        
    Returns:
        Sum or None
    """
    items = [_float_or_none(value) for value in values]
    present = [value for value in items if value is not None]
    return sum(present) if present else None


def _sum_node_earnings(earnings: object) -> float | None:
    """Sum node earnings.
    
    Args:
        earnings: Earnings data
        
    Returns:
        Total earnings or None
    """
    if not isinstance(earnings, list):
        return None
    total = 0.0
    for item in earnings:
        if isinstance(item, dict):
            total += _float_or_none(item.get("etherAmount")) or 0.0
    return total


def _first_network_ip(node: dict[str, Any]) -> str | None:
    """Extract the first network IP from node data.
    
    Args:
        node: Node data
        
    Returns:
        First network IP or None
    """
    networks = node.get("networks") or {}
    if not isinstance(networks, dict):
        return None
    for network in networks.values():
        if isinstance(network, dict) and network.get("ip"):
            return str(network["ip"])
    return None


def _bool_number(value: Any) -> float | None:
    """Convert a boolean value to a number.
    
    Args:
        value: Value to convert
        
    Returns:
        1.0 if True, 0.0 if False, None if None
    """
    if value is None:
        return None
    return 1.0 if bool(value) else 0.0


def _float_or_none(value: Any) -> float | None:
    """Convert a value to float or return None.
    
    Args:
        value: Value to convert
        
    Returns:
        Float value or None
    """
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> datetime | None:
    """Parse a time string.
    
    Args:
        value: Time string to parse
        
    Returns:
        Parsed datetime or None
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
