"""Scheduler for MystMon data collection.

This module coordinates the periodic collection of metrics from various sources
including Docker containers, Prometheus endpoints, SNMP targets, and Mysterium
node TequilAPI endpoints. It manages the collection cycle timing and ensures
data is properly stored in both reading storage and history database.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from mystmon.collectors.myst import collect_myst
from mystmon.collectors.mystnodes import collect_mystnodes_portal_accounts, _match_local_nodes
from mystmon.collectors.prometheus import collect_prometheus
from mystmon.collectors.snmp import collect_snmp
from mystmon.collectors.system import collect_system
from mystmon.snapshot import render_snmp_extend
from mystmon.storage import Reading
from mystmon.timeutils import now_local

if TYPE_CHECKING:
    from mystmon.config import MystMonConfig
    from mystmon.history import HistoryStore
    from mystmon.storage import ReadingStore
    from mystmon.telegram import TelegramNotifier
    from mystmon.alerting import AlertManager

LOGGER = logging.getLogger(__name__)


class CollectorScheduler:
    """Scheduler for periodic data collection.
    
    Coordinates collection cycles from all configured sources and manages
    the storage of collected data in both reading storage and history.
    """
    
    def __init__(
        self,
        config: MystMonConfig,
        store: ReadingStore,
        history: HistoryStore | None = None,
        telegram: TelegramNotifier | None = None,
        alert_manager: AlertManager | None = None,
    ) -> None:
        """Initialize the collector scheduler.
        
        Args:
            config: MystMon configuration
            store: Reading storage for current metrics
            history: History storage for persistent data (optional)
            telegram: Telegram notifier for alerts (optional)
            alert_manager: Alert manager for alert evaluation (optional)
        """
        self.config = config
        self.store = store
        self.history = history
        self.telegram = telegram
        self.alert_manager = alert_manager
        self._stop_event = asyncio.Event()
        self._collection_counts: dict[str, int] = {}
        self._last_alert_evaluation = datetime.now()
    
    def stop(self) -> None:
        """Signal the scheduler to stop."""
        self._stop_event.set()
    
    async def run_forever(self) -> None:
        """Run the collection scheduler indefinitely.
        
        Executes collection cycles at the configured interval until stopped.
        """
        LOGGER.info("Starting collector scheduler with interval=%ds", self.config.service.poll_interval_seconds)
        while not self._stop_event.is_set():
            try:
                await self.collect_once()
                # Evaluate alerts if alerting is enabled
                if self.alert_manager and self.config.alerting.enabled:
                    await self._evaluate_alerts()
            except Exception:
                LOGGER.exception("Collection cycle failed")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.config.service.poll_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass  # Normal timeout, continue to next collection
        LOGGER.info("Collector scheduler stopped")
    
    async def collect_once(self) -> dict[str, int]:
        """Execute a single collection cycle.
        
        Collects data from all configured sources and updates storage.
        
        Returns:
            Dictionary with collection counts by source type
        """
        LOGGER.info("Starting collection cycle")
        start_time = time.monotonic()
        counts: dict[str, int] = {}
        
        # Collect from Prometheus endpoints
        prometheus_readings = []
        for target in self.config.prometheus.targets:
            try:
                readings = await collect_prometheus(target, self.config.service.request_timeout_seconds)
                prometheus_readings.extend(readings)
            except Exception:
                LOGGER.exception("Prometheus collection failed for target=%s", target.name)
        for reading in prometheus_readings:
            self.store.add(reading)
        counts["prometheus"] = len(prometheus_readings)
        LOGGER.info("Collected prometheus metrics count=%d", len(prometheus_readings))
        
        # Collect from SNMP targets
        snmp_readings = []
        for target in self.config.snmp.targets:
            try:
                readings = await collect_snmp(
                    target,
                    self.config.snmp.default_community,
                    self.config.service.request_timeout_seconds,
                )
                snmp_readings.extend(readings)
            except Exception:
                LOGGER.exception("SNMP collection failed for target=%s", target.name)
        for reading in snmp_readings:
            self.store.add(reading)
        counts["snmp"] = len(snmp_readings)
        LOGGER.info("Collected snmp metrics count=%d", len(snmp_readings))
        
        # Collect from MystNodes portal
        portal_data = await collect_mystnodes_portal_accounts(
            self.config.mystnodes_accounts,
            self.config.service.request_timeout_seconds,
            [],
        )
        portal_snapshot = self._normalize_portal_snapshot(portal_data)
        counts["mystnodes"] = len(portal_snapshot.get("accounts", []))
        LOGGER.info("Collected mystnodes data count=%d", counts["mystnodes"])

        # Collect from portal-derived local runtimes plus configured remote hosts.
        myst_readings = await collect_myst(
            self.config.myst,
            self.config.service.request_timeout_seconds,
            portal_snapshot.get("nodes") or [],
        )
        for reading in myst_readings:
            self.store.add(reading)
        local_runtime_nodes = self._dedupe_myst_nodes(
            [reading.raw_data for reading in myst_readings if reading.source_type == "myst" and reading.raw_data]
        )
        counts["myst"] = len(local_runtime_nodes)
        LOGGER.info(
            "Collected myst runtime nodes=%d metric_readings=%d",
            counts["myst"],
            len(myst_readings),
        )
        portal_snapshot["local_matches"] = _match_local_nodes(
            portal_snapshot.get("nodes") or [],
            local_runtime_nodes,
        )
        
        # Collect system metrics
        system_readings = await collect_system(self.config.service.request_timeout_seconds)
        for reading in system_readings:
            self.store.add(reading)
        counts["system"] = len(system_readings)
        LOGGER.info("Collected system metrics count=%d", len(system_readings))
        
        # Snapshot counts are per collection cycle, not cumulative totals.
        self._collection_counts = counts.copy()

        snapshot = self._build_snapshot(myst_readings, portal_snapshot)
        
        # Save snapshot to file
        self._save_snapshot(snapshot)
        
        # Save to history if enabled
        collection_id = None
        if self.history is not None:
            try:
                collection_id = self.history.append_snapshot(snapshot)
                LOGGER.info("Saved collection to history id=%s", collection_id)
            except Exception:
                LOGGER.exception("Failed to save collection to history")
        
        # Generate SNMP extend script if configured
        if self.config.outputs.snmp_extend_path:
            try:
                script_content = render_snmp_extend(snapshot)
                Path(self.config.outputs.snmp_extend_path).write_text(script_content, encoding="utf-8")
                LOGGER.info("Generated SNMP extend script path=%s", self.config.outputs.snmp_extend_path)
            except Exception:
                LOGGER.exception("Failed to generate SNMP extend script")
        
        # Export CSV if configured
        if hasattr(self.config.outputs, 'csv_export_path') and self.config.outputs.csv_export_path and collection_id is not None:
            try:
                from mystmon.export_csv import write_collection_csv_exports
                write_collection_csv_exports(
                    snapshot,
                    self.config.outputs.csv_export_path,
                    collection_id,
                )
                LOGGER.info("Exported CSV data path=%s collection_id=%s", self.config.outputs.csv_export_path, collection_id)
            except Exception:
                LOGGER.exception("Failed to export CSV data")
        
        # Send Telegram report if configured and time is right
        if self.telegram is not None and self.history is not None:
            try:
                await self._maybe_send_telegram_report()
            except Exception:
                LOGGER.exception("Failed to send Telegram report")
        
        elapsed = time.monotonic() - start_time
        LOGGER.info("Collection cycle completed elapsed=%.2fs counts=%s", elapsed, counts)
        return counts
    
    def _build_snapshot(
        self,
        myst_readings: list,
        portal_data: dict | None,
    ) -> dict:
        """Build a snapshot of the current state.
        
        Args:
            myst_readings: Readings from Myst containers/hosts
            portal_data: Data from MystNodes portal
            
        Returns:
            Dictionary representing the current snapshot
        """
        nodes = []
        for reading in myst_readings:
            if reading.source_type == "myst" and reading.raw_data:
                self._merge_myst_node(nodes, reading.raw_data)

        portal_snapshot = self._normalize_portal_snapshot(portal_data)
        self._apply_portal_matches(nodes, portal_snapshot)
        return {
            "generated_at": now_local(self.config.service.timezone).isoformat(),
            "nodes": nodes,
            "mystnodes": portal_snapshot,
            "collection_counts": self._collection_counts.copy(),
        }

    def _normalize_portal_snapshot(self, portal_data: object) -> dict:
        if portal_data is None:
            return {"accounts": [], "nodes": [], "local_matches": {}, "node_details": {"nodes": {}}}
        if isinstance(portal_data, dict):
            normalized = dict(portal_data)
            normalized.setdefault("accounts", [])
            normalized.setdefault("nodes", [])
            normalized.setdefault("local_matches", self._merge_local_matches(normalized.get("accounts", [])))
            normalized.setdefault("node_details", self._merge_node_details(normalized.get("accounts", [])))
            return normalized
        if isinstance(portal_data, list):
            accounts = [account for account in portal_data if isinstance(account, dict)]
            return {
                "accounts": accounts,
                "nodes": self._merge_portal_nodes(accounts),
                "local_matches": self._merge_local_matches(accounts),
                "node_details": self._merge_node_details(accounts),
            }
        return {"accounts": [], "nodes": [], "local_matches": {}, "node_details": {"nodes": {}}}

    async def _collect_portal_local_nodes(self, portal_snapshot: dict) -> list:
        local_matches = portal_snapshot.get("local_matches") or {}
        portal_nodes_by_id = {
            str(node.get("id") or ""): node
            for node in (portal_snapshot.get("nodes") or [])
            if isinstance(node, dict) and node.get("id")
        }
        detail_nodes = ((portal_snapshot.get("node_details") or {}).get("nodes")) or {}
        rows: list[dict] = []
        for node_id, match in local_matches.items():
            if not isinstance(match, dict):
                continue
            portal_node = portal_nodes_by_id.get(str(node_id), {})
            detail = ((detail_nodes.get(str(node_id)) or {}).get("detail") or {}).get("data") or {}
            row = dict(match)
            row["portal_account"] = portal_node.get("account", "")
            row["portal_identity"] = portal_node.get("identity", "")
            row["portal_node_name"] = portal_node.get("name", "")
            row["portal_local_ip"] = portal_node.get("localIp", "")
            row["host"] = row.get("host") or portal_node.get("localIp", "")
            api = dict(row.get("api") or {})
            api.setdefault("identity", portal_node.get("identity", ""))
            metrics = dict(api.get("metrics") or {})
            if metrics.get("provider_quality") in (None, ""):
                metrics["provider_quality"] = ((portal_node.get("nodeStatus") or {}).get("quality"))
            api["metrics"] = metrics
            api.setdefault("endpoints", {})
            row["api"] = api
            if detail:
                row["portal_detail"] = detail
            rows.append(row)
        return rows

    def _portal_local_node_readings(self, nodes: list[dict]) -> list[Reading]:
        timestamp = datetime.now()
        readings: list[Reading] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            source_name = str(node.get("name") or node.get("container_name") or node.get("host") or "portal-local-node")
            readings.append(
                Reading(
                    source_type="myst",
                    source_name=source_name,
                    metric_name="running",
                    value=1.0 if node.get("running") else 0.0,
                    labels={},
                    timestamp=timestamp,
                    raw_data=self._normalize_portal_local_node(node),
                )
            )
        return readings

    def _normalize_portal_local_node(self, node: dict) -> dict:
        normalized = dict(node)
        tequilapi = normalized.pop("tequilapi", None)
        if tequilapi is not None and "api" not in normalized:
            normalized["api"] = tequilapi
        if "portal_account" not in normalized and normalized.get("account"):
            normalized["portal_account"] = normalized.get("account")
        if "portal_identity" not in normalized and normalized.get("identity"):
            normalized["portal_identity"] = normalized.get("identity")
        return normalized

    def _merge_myst_node(self, nodes: list[dict], raw_data: dict) -> None:
        key = (
            str(raw_data.get("host") or ""),
            str(raw_data.get("container_name") or raw_data.get("name") or ""),
        )
        for existing in nodes:
            existing_key = (
                str(existing.get("host") or ""),
                str(existing.get("container_name") or existing.get("name") or ""),
            )
            if existing_key != key:
                continue
            self._merge_node_data(existing, raw_data)
            return
        nodes.append(dict(raw_data))

    def _merge_node_data(self, existing: dict, incoming: dict) -> None:
        for key, value in incoming.items():
            if isinstance(value, dict) and isinstance(existing.get(key), dict):
                self._merge_node_data(existing[key], value)
            elif value not in (None, "", [], {}):
                existing[key] = value

    def _dedupe_myst_nodes(self, raw_nodes: list[dict]) -> list[dict]:
        deduped: list[dict] = []
        for raw_node in raw_nodes:
            if not isinstance(raw_node, dict):
                continue
            self._merge_myst_node(deduped, raw_node)
        return deduped

    def _apply_portal_matches(self, nodes: list[dict], portal_snapshot: dict) -> None:
        portal_nodes = {
            str(node.get("id") or ""): node
            for node in (portal_snapshot.get("nodes") or [])
            if isinstance(node, dict) and node.get("id")
        }
        for node_id, match in (portal_snapshot.get("local_matches") or {}).items():
            if not isinstance(match, dict):
                continue
            portal_node = portal_nodes.get(str(node_id), {})
            host = str(match.get("host") or portal_node.get("localIp") or "")
            container_name = str(match.get("container_name") or match.get("name") or portal_node.get("name") or "")
            for node in nodes:
                node_host = str(node.get("host") or "")
                node_container = str(node.get("container_name") or node.get("name") or "")
                if node_host != host:
                    continue
                if container_name and node_container and node_container != container_name:
                    continue
                node["local_match"] = True
                node.setdefault("portal_account", portal_node.get("account", ""))
                node.setdefault("portal_identity", portal_node.get("identity", ""))
                node.setdefault("portal_node_name", portal_node.get("name", ""))
                node.setdefault("portal_local_ip", portal_node.get("localIp", ""))
                break

    def _merge_portal_nodes(self, accounts: list[dict]) -> list[dict]:
        nodes: list[dict] = []
        for account in accounts:
            account_name = str(account.get("name", ""))
            endpoint_nodes = (((account.get("endpoints") or {}).get("nodes") or {}).get("data") or {}).get("nodes") or []
            for node in endpoint_nodes:
                if not isinstance(node, dict):
                    continue
                merged = dict(node)
                merged.setdefault("account", account_name)
                nodes.append(merged)
        return nodes

    def _merge_local_matches(self, accounts: list[dict]) -> dict:
        matches: dict = {}
        for account in accounts:
            account_matches = account.get("local_matches") or {}
            if isinstance(account_matches, dict):
                matches.update(account_matches)
        return matches

    def _merge_node_details(self, accounts: list[dict]) -> dict:
        nodes: dict = {}
        for account in accounts:
            account_nodes = ((account.get("node_details") or {}).get("nodes")) or {}
            if isinstance(account_nodes, dict):
                nodes.update(account_nodes)
        return {"nodes": nodes}
    
    def _save_snapshot(self, snapshot: dict) -> None:
        """Save snapshot to the configured JSON file.
        
        Args:
            snapshot: Snapshot data to save
        """
        try:
            path = Path(self.config.outputs.latest_json_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
            LOGGER.info("Saved snapshot path=%s", path)
        except Exception:
            LOGGER.exception("Failed to save snapshot path=%s", self.config.outputs.latest_json_path)
    
    async def _maybe_send_telegram_report(self) -> None:
        """Send Telegram report if it's time to do so."""
        if self.telegram is None or self.history is None:
            return
            
        now = datetime.now(UTC)
        report_date = now.strftime("%Y-%m-%d")
        
        # Parse report time from config
        try:
            report_hour, report_minute = map(int, self.config.telegram.report_time_local.split(":"))
        except (ValueError, AttributeError):
            report_hour, report_minute = 8, 0  # Default to 8:00 AM
            
        # Check if we should send a report (daily at configured time)
        if now.hour == report_hour and now.minute >= report_minute and now.minute < report_minute + 5:
            if not self.history.report_sent(report_date):
                try:
                    await self.telegram.send_report()
                    self.history.record_report(
                        report_date,
                        24,
                        "sent",
                        "Daily report sent successfully",
                    )
                except Exception as e:
                    LOGGER.error("Failed to send Telegram report: %s", e)
                    self.history.record_report(
                        report_date,
                        24,
                        "failed",
                        f"Failed to send report: {e}",
                    )
    
    async def _evaluate_alerts(self) -> None:
        """Evaluate alerts based on current readings."""
        if not self.alert_manager or not self.config.alerting.enabled:
            return
            
        now = datetime.now()
        # Only evaluate alerts at the configured interval
        if (now - self._last_alert_evaluation).seconds < self.config.alerting.evaluation_interval_seconds:
            return
            
        LOGGER.debug("Evaluating alerts")
        try:
            alerts = self.alert_manager.evaluate_all_readings(self.store)
            if alerts:
                LOGGER.info("Found %d active alerts", len(alerts))
                # In a full implementation, we would send notifications here
                # For now, we'll just log them
                for alert in alerts:
                    LOGGER.warning(
                        "ALERT: %s - %s (Severity: %s)",
                        alert.name,
                        alert.summary,
                        alert.severity.value
                    )
            self._last_alert_evaluation = now
        except Exception:
            LOGGER.exception("Failed to evaluate alerts")
