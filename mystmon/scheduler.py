from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from mystmon.collectors.myst import collect_myst_nodes_async
from mystmon.collectors.mystnodes import collect_mystnodes_portal_accounts
from mystmon.collectors.prometheus import collect_prometheus
from mystmon.collectors.snmp import collect_snmp
from mystmon.config import MystMonConfig
from mystmon.history import HistoryStore
from mystmon.snapshot import build_snapshot, write_snapshot
from mystmon.storage import Reading, ReadingStore
from mystmon.telegram import TelegramNotifier, next_report_delay

LOGGER = logging.getLogger(__name__)


class CollectorScheduler:
    """Scheduler for collecting metrics from various sources at regular intervals."""
    
    def __init__(
        self,
        config: MystMonConfig,
        store: ReadingStore,
        history: HistoryStore | None = None,
        telegram: TelegramNotifier | None = None,
    ) -> None:
        """Initialize the collector scheduler.
        
        Args:
            config: Configuration for the collector
            store: Storage for collected readings
            history: Optional history storage
            telegram: Optional telegram notifier
        """
        self.config = config
        self.store = store
        self.history = history
        self.telegram = telegram
        self._running = False
        self._collect_task: asyncio.Task[None] | None = None
        self._daily_report_task: asyncio.Task[None] | None = None

    async def run_forever(self) -> None:
        """Run the collector scheduler indefinitely."""
        self._running = True
        try:
            # Run initial collection
            await self.collect_once()
            
            # Schedule daily reports if telegram is enabled
            if self.telegram and self.config.telegram.enabled:
                self._daily_report_task = asyncio.create_task(self._run_daily_reports())
            
            # Run periodic collection
            while self._running:
                await asyncio.sleep(self.config.service.poll_interval_seconds)
                if self._running:
                    await self.collect_once()
        except asyncio.CancelledError:
            LOGGER.info("Collector scheduler cancelled")
        except Exception as exc:
            LOGGER.exception("Collector scheduler failed: %s", exc)
            raise

    def stop(self) -> None:
        """Stop the collector scheduler."""
        self._running = False
        if self._collect_task:
            self._collect_task.cancel()
        if self._daily_report_task:
            self._daily_report_task.cancel()

    async def collect_once(self) -> dict[str, int]:
        """Run a single collection cycle.
        
        Returns:
            Dictionary with counts of collected items from each source
        """
        LOGGER.info("Starting collection cycle")
        start_time = time.monotonic()
        collection_counts: dict[str, int] = {}
        
        try:
            # Collect Prometheus targets
            if self.config.prometheus.enabled:
                prometheus_readings = await self._collect_prometheus_targets()
                self.store.replace_source("prometheus", "prometheus", prometheus_readings)
                collection_counts["prometheus"] = len(prometheus_readings)
            
            # Collect SNMP targets
            if self.config.snmp.enabled:
                snmp_readings = await self._collect_snmp_targets()
                self.store.replace_source("snmp", "snmp", snmp_readings)
                collection_counts["snmp"] = len(snmp_readings)
            
            # Collect MYST nodes
            if self.config.myst.enabled:
                myst_readings = await self._collect_myst_nodes()
                self.store.replace_source("myst", "myst", myst_readings)
                collection_counts["myst"] = len(myst_readings)
            
            # Collect portal data
            portal_data = None
            local_nodes = []
            if self.config.mystnodes_accounts:
                local_nodes = await self._collect_portal_local_nodes()
                portal_data = await self._collect_portal_data(local_nodes)
                # Count total nodes across all accounts
                total_portal_nodes = self._count_portal_nodes(portal_data)
                collection_counts["portal_nodes"] = total_portal_nodes
                if collection_counts.get("myst", 0) == 0 and total_portal_nodes:
                    collection_counts["myst"] = total_portal_nodes
            
            # Build and write snapshot
            nodes = [r.as_dict() for r in self.store.all() if r.source_type == "myst"]
            mystnodes_payload = None
            if portal_data:
                if isinstance(portal_data, dict):
                    mystnodes_payload = portal_data
                else:
                    mystnodes_payload = {"accounts": portal_data}
                    if local_nodes:
                        mystnodes_payload["local_nodes"] = local_nodes
            snapshot = build_snapshot(nodes, collection_counts, mystnodes_payload)
            try:
                write_snapshot(
                    snapshot,
                    self.config.outputs.latest_json_path,
                    self.config.outputs.snmp_extend_path,
                )
            except OSError as exc:
                LOGGER.warning("Skipping snapshot file write path=%s reason=%s", self.config.outputs.latest_json_path, exc)
            
            # Store in history if enabled
            if self.history:
                collection_id = self.history.append_snapshot(snapshot)
                LOGGER.info("Snapshot stored in history with ID %d", collection_id)
            
            duration = time.monotonic() - start_time
            LOGGER.info(
                "Collection cycle completed duration=%.2fs counts=%s",
                duration,
                collection_counts,
            )
            return collection_counts
        except Exception as exc:
            LOGGER.exception("Collection cycle failed: %s", exc)
            raise

    async def _collect_prometheus_targets(self) -> list[Reading]:
        """Collect from all Prometheus targets.
        
        Returns:
            List of readings from Prometheus targets
        """
        readings: list[Reading] = []
        for target in self.config.prometheus.targets:
            try:
                target_readings = await collect_prometheus(target, self.config.service.request_timeout_seconds)
                readings.extend(target_readings)
                LOGGER.info("Collected %d readings from Prometheus target %s", len(target_readings), target.name)
            except Exception as exc:
                LOGGER.error("Failed to collect from Prometheus target %s: %s", target.name, exc)
        return readings

    async def _collect_snmp_targets(self) -> list[Reading]:
        """Collect from all SNMP targets.
        
        Returns:
            List of readings from SNMP targets
        """
        readings: list[Reading] = []
        for target in self.config.snmp.targets:
            try:
                target_readings = await collect_snmp(
                    target,
                    self.config.snmp.default_community,
                    self.config.service.request_timeout_seconds,
                )
                readings.extend(target_readings)
                LOGGER.info("Collected %d readings from SNMP target %s", len(target_readings), target.name)
            except Exception as exc:
                LOGGER.error("Failed to collect from SNMP target %s: %s", target.name, exc)
        return readings

    async def _collect_myst_nodes(self) -> list[Reading]:
        """Collect MYST nodes and convert to readings.
        
        Returns:
            List of readings from MYST nodes
        """
        try:
            nodes = await collect_myst_nodes_async(
                self.config.myst,
                self.config.service.request_timeout_seconds,
                self.config.service.log_window_seconds,
                self.config.mystnodes_accounts,
            )
            readings = []
            for node in nodes:
                readings.append(Reading(
                    source_type="myst",
                    source_name=node.get("name", "unknown"),
                    metric_name="node_info",
                    value=1.0,
                    labels={
                        "container_name": str(node.get("container_name", "")),
                        "host": str(node.get("host", "")),
                        "status": str(node.get("status", "unknown")),
                    },
                    timestamp=datetime.now(UTC),
                    raw_data=node,
                ))
                # Add uptime metric
                uptime = node.get("uptime_seconds")
                if uptime is not None:
                    readings.append(Reading(
                        source_type="myst",
                        source_name=node.get("name", "unknown"),
                        metric_name="node_uptime_seconds",
                        value=float(uptime),
                        labels={},
                        timestamp=datetime.now(UTC),
                        raw_data=None,
                    ))
                # Add restart count metric
                restarts = node.get("restart_count")
                if restarts is not None:
                    readings.append(Reading(
                        source_type="myst",
                        source_name=node.get("name", "unknown"),
                        metric_name="node_restart_count",
                        value=float(restarts),
                        labels={},
                        timestamp=datetime.now(UTC),
                        raw_data=None,
                    ))
            LOGGER.info("Collected %d MYST nodes", len(nodes))
            return readings
        except Exception as exc:
            LOGGER.error("Failed to collect MYST nodes: %s", exc)
            return []

    async def _collect_portal_data(self, local_nodes: list[dict[str, Any]] | None = None) -> list[dict[str, Any]] | None:
        """Collect portal data from all accounts.
        
        Returns:
            List of portal account data or None if collection failed
        """
        try:
            portal_data = await collect_mystnodes_portal_accounts(
                configs=self.config.mystnodes_accounts,
                timeout_seconds=self.config.service.request_timeout_seconds,
                local_nodes=local_nodes,
            )
            LOGGER.info("Collected portal data from %d accounts", len(portal_data or []))
            return portal_data
        except Exception as exc:
            LOGGER.error("Failed to collect portal data: %s", exc)
            return None

    async def _collect_portal_local_nodes(self) -> list[dict[str, Any]]:
        """Collect local portal node data for portal-to-local matching."""
        return []

    def _count_portal_nodes(self, portal_data: Any) -> int:
        if isinstance(portal_data, dict):
            nodes = portal_data.get("nodes", [])
            if isinstance(nodes, list):
                return len(nodes)
            return 0
        if isinstance(portal_data, list):
            total = 0
            for account_data in portal_data:
                if not isinstance(account_data, dict):
                    continue
                nodes = account_data.get("nodes")
                if isinstance(nodes, list):
                    total += len(nodes)
                elif isinstance(nodes, dict):
                    data_nodes = nodes.get("data")
                    if isinstance(data_nodes, dict) and isinstance(data_nodes.get("nodes"), list):
                        total += len(data_nodes["nodes"])
                    elif isinstance(data_nodes, list):
                        total += len(data_nodes)
                    elif isinstance(nodes.get("nodes"), list):
                        total += len(nodes["nodes"])
                    elif isinstance(nodes.get("data"), list):
                        total += len(nodes["data"])
                else:
                    endpoints = account_data.get("endpoints") or {}
                    nodes_endpoint = endpoints.get("nodes") or {}
                    data = nodes_endpoint.get("data") if isinstance(nodes_endpoint, dict) else None
                    if isinstance(data, dict) and isinstance(data.get("nodes"), list):
                        total += len(data["nodes"])
                    elif isinstance(data, list):
                        total += len(data)
            return total
        return 0

    async def _run_daily_reports(self) -> None:
        """Run daily reports."""
        try:
            while self._running:
                delay = next_report_delay(self.config.telegram)
                LOGGER.info("Next telegram report scheduled in %.1f seconds", delay)
                await asyncio.sleep(delay)
                if self._running and self.telegram:
                    try:
                        await self.telegram.send_report()
                    except Exception as exc:
                        LOGGER.error("Failed to send telegram report: %s", exc)
        except asyncio.CancelledError:
            LOGGER.info("Daily report task cancelled")
        except Exception as exc:
            LOGGER.exception("Daily report task failed: %s", exc)
