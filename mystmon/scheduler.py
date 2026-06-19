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
from mystmon.collectors.mystnodes import collect_mystnodes_portal_accounts
from mystmon.collectors.prometheus import collect_prometheus
from mystmon.collectors.snmp import collect_snmp
from mystmon.snapshot import render_snmp_extend

if TYPE_CHECKING:
    from mystmon.config import MystMonConfig
    from mystmon.history import HistoryStore
    from mystmon.storage import ReadingStore
    from mystmon.telegram import TelegramNotifier

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
        history: HistoryStore | None,
        telegram: TelegramNotifier | None,
    ) -> None:
        """Initialize the collector scheduler.
        
        Args:
            config: MystMon configuration
            store: Reading storage for current metrics
            history: History storage for persistent data (optional)
            telegram: Telegram notifier for alerts (optional)
        """
        self.config = config
        self.store = store
        self.history = history
        self.telegram = telegram
        self._stop_event = asyncio.Event()
        self._collection_counts: dict[str, int] = {}
    
    def stop(self) -> None:
        """Signal the scheduler to stop."""
        self._stop_event.set()
    
    async def run_forever(self) -> None:
        """Run the collection scheduler indefinitely.
        
        Executes collection cycles at the configured interval until stopped.
        """
        LOGGER.info("Starting collector scheduler with interval=%ds", self.config.collection.interval_seconds)
        while not self._stop_event.is_set():
            try:
                await self.collect_once()
            except Exception:
                LOGGER.exception("Collection cycle failed")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.config.collection.interval_seconds,
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
        
        # Collect from Myst containers/hosts
        myst_readings = await collect_myst(
            self.config.collectors.myst,
            self.config.collection.timeout_seconds,
        )
        for reading in myst_readings:
            self.store.add(reading)
        counts["myst"] = len(myst_readings)
        LOGGER.info("Collected myst metrics count=%d", len(myst_readings))
        
        # Collect from Prometheus endpoints
        prometheus_readings = []
        for target in self.config.collectors.prometheus:
            try:
                readings = await collect_prometheus(target, self.config.collection.timeout_seconds)
                prometheus_readings.extend(readings)
            except Exception:
                LOGGER.exception("Prometheus collection failed for target=%s", target.name)
        for reading in prometheus_readings:
            self.store.add(reading)
        counts["prometheus"] = len(prometheus_readings)
        LOGGER.info("Collected prometheus metrics count=%d", len(prometheus_readings))
        
        # Collect from SNMP targets
        snmp_readings = []
        for target in self.config.collectors.snmp:
            try:
                readings = await collect_snmp(
                    target,
                    self.config.collection.default_snmp_community,
                    self.config.collection.timeout_seconds,
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
            self.config.collectors.mystnodes.accounts,
            self.config.collection.timeout_seconds,
            [reading.raw_data for reading in myst_readings if reading.source_type == "myst"],
        )
        counts["mystnodes"] = len(portal_data) if portal_data else 0
        LOGGER.info("Collected mystnodes data count=%d", counts["mystnodes"])
        
        # Build snapshot
        snapshot = self._build_snapshot(myst_readings, portal_data)
        
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
        if self.config.outputs.csv_export_path and collection_id is not None:
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
        
        # Update collection counts
        for key, count in counts.items():
            self._collection_counts[key] = self._collection_counts.get(key, 0) + count
        
        elapsed = time.monotonic() - start_time
        LOGGER.info("Collection cycle completed elapsed=%.2fs counts=%s", elapsed, counts)
        return counts
    
    def _build_snapshot(
        self,
        myst_readings: list,
        portal_data: list | None,
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
                nodes.append(reading.raw_data)
        
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "nodes": nodes,
            "mystnodes": {
                "accounts": portal_data or [],
            },
            "collection_counts": self._collection_counts.copy(),
        }
    
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
        
        # Check if we should send a report (daily at configured time)
        if now.hour == self.config.telegram.daily_report_hour and now.minute < 5:
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
