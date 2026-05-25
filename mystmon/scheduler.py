from __future__ import annotations

import asyncio
import logging

from mystmon.collectors import collect_myst_nodes, collect_mystnodes_portal, collect_prometheus, collect_snmp
from mystmon.config import MystMonConfig
from mystmon.history import HistoryStore
from mystmon.snapshot import build_snapshot, write_snapshot
from mystmon.storage import ReadingStore
from mystmon.telegram import TelegramNotifier, next_report_delay

LOGGER = logging.getLogger(__name__)


class CollectorScheduler:
    def __init__(
        self,
        config: MystMonConfig,
        store: ReadingStore,
        history: HistoryStore | None = None,
        telegram: TelegramNotifier | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.history = history
        self.telegram = telegram
        self._stop_event = asyncio.Event()

    async def run_forever(self) -> None:
        report_task = None
        if self.config.telegram.enabled and self.telegram is not None:
            report_task = asyncio.create_task(self._run_daily_reports())
        while not self._stop_event.is_set():
            await self.collect_once()
            try:
                LOGGER.info(
                    "MystMon collection sleeping for %s seconds",
                    self.config.service.poll_interval_seconds,
                )
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.config.service.poll_interval_seconds,
                )
            except TimeoutError:
                continue
        if report_task is not None:
            report_task.cancel()
            try:
                await report_task
            except asyncio.CancelledError:
                pass

    def stop(self) -> None:
        self._stop_event.set()

    async def collect_once(self) -> dict[str, int]:
        timeout = self.config.service.request_timeout_seconds
        counts = {"myst": 0, "mystnodes": 0, "prometheus": 0, "snmp": 0}
        myst_nodes = []
        mystnodes_portal = None
        LOGGER.info("MystMon collection started")

        if self.config.myst.enabled:
            try:
                myst_nodes = await collect_myst_nodes(
                    self.config.myst,
                    timeout,
                    self.config.service.log_window_seconds,
                )
                counts["myst"] = len(myst_nodes)
            except Exception:
                LOGGER.exception("MYST Docker collection failed")

        if self.config.mystnodes.enabled:
            try:
                mystnodes_portal = await collect_mystnodes_portal(self.config.mystnodes, timeout, myst_nodes)
                counts["mystnodes"] = len(mystnodes_portal.get("endpoints", {}))
            except Exception:
                LOGGER.exception("MystNodes portal collection failed")

        if self.config.prometheus.enabled:
            for target in self.config.prometheus.targets:
                try:
                    readings = await collect_prometheus(target, timeout)
                    self.store.replace_source("prometheus", target.name, readings)
                    counts["prometheus"] += len(readings)
                except Exception:
                    LOGGER.exception("Prometheus collection failed for %s", target.name)

        if self.config.snmp.enabled:
            for target in self.config.snmp.targets:
                try:
                    readings = await collect_snmp(target, self.config.snmp.default_community, timeout)
                    self.store.replace_source("snmp", target.name, readings)
                    counts["snmp"] += len(readings)
                except Exception:
                    LOGGER.exception("SNMP collection failed for %s", target.name)

        snapshot = build_snapshot(myst_nodes, counts, mystnodes_portal)
        write_snapshot(
            snapshot,
            self.config.outputs.latest_json_path,
            self.config.outputs.snmp_extend_path,
        )
        if self.history is not None and self.config.history.enabled:
            collection_id = self.history.append_snapshot(snapshot)
            LOGGER.info("MystMon collection persisted collection_id=%s", collection_id)
        LOGGER.info("MystMon collection completed counts=%s", counts)
        return counts

    async def _run_daily_reports(self) -> None:
        while not self._stop_event.is_set():
            delay = next_report_delay(self.config.telegram)
            LOGGER.info("MystMon Telegram report sleeping for %.0f seconds", delay)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                continue
            except TimeoutError:
                pass
            if self.telegram is None:
                continue
            try:
                result = await self.telegram.send_report(hours=24, force=False)
                LOGGER.info("MystMon Telegram report result=%s", result)
            except Exception:
                LOGGER.exception("MystMon Telegram report failed")
