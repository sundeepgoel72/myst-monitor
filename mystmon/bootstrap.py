from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from mystmon.snapshot import render_snmp_extend

LOGGER = logging.getLogger(__name__)


def bootstrap_storage(db_path: str, latest_json_path: str, snmp_extend_path: str) -> None:
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    _bootstrap_database(db_file)

    latest_path = Path(latest_json_path)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.touch(exist_ok=True)

    snmp_path = Path(snmp_extend_path)
    snmp_path.parent.mkdir(parents=True, exist_ok=True)
    snmp_path.touch(exist_ok=True)


def _bootstrap_database(db_file: Path) -> None:
    LOGGER.info("Bootstrapping MystMon storage path=%s", db_file)
    with sqlite3.connect(db_file) as db:
        db.row_factory = sqlite3.Row
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
        _ensure_node_metric_columns(db)


def _ensure_node_metric_columns(db: sqlite3.Connection) -> None:
    columns = {
        "api_enabled": "REAL",
        "api_up": "REAL",
        "api_auth": "REAL",
        "api_schema_available": "REAL",
        "api_last_check": "TEXT",
        "api_base_url": "TEXT",
        "api_status_code": "REAL",
        "api_identity": "TEXT",
        "api_public_ip": "TEXT",
        "api_location_city": "TEXT",
        "api_location_country": "TEXT",
        "api_location_isp": "TEXT",
        "api_location_asn": "TEXT",
        "api_nat_type": "TEXT",
        "api_services_count": "REAL",
        "api_services_running": "REAL",
        "api_service_types": "TEXT",
        "api_sessions_active": "REAL",
        "api_sessions_1d": "REAL",
        "api_sessions_7d": "REAL",
        "api_provider_quality": "REAL",
        "api_provider_transferred_data": "REAL",
        "api_payments_balance": "REAL",
        "api_settlements_count": "REAL",
        "api_config_present": "REAL",
    }
    existing = {row["name"] for row in db.execute("PRAGMA table_info(node_metrics)").fetchall()}
    for column, column_type in columns.items():
        if column in existing:
            continue
        db.execute(f"ALTER TABLE node_metrics ADD COLUMN {column} {column_type}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Bootstrap MystMon storage artifacts.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--latest-json-path", required=True)
    parser.add_argument("--snmp-extend-path", required=True)
    args = parser.parse_args()
    bootstrap_storage(args.db_path, args.latest_json_path, args.snmp_extend_path)
