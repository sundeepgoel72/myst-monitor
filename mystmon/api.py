from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CollectorRegistry, Gauge, generate_latest

from mystmon import __version__
from mystmon.config import MystMonConfig, load_config
from mystmon.history import HistoryStore
from mystmon.scheduler import CollectorScheduler
from mystmon.storage import ReadingStore
from mystmon.telegram import TelegramNotifier
from mystmon.ui import create_ui_router


def create_app(config: MystMonConfig | None = None) -> FastAPI:
    app_config = config or load_config()
    store = ReadingStore()
    history = HistoryStore(app_config.history.db_path) if app_config.history.enabled else None
    telegram = TelegramNotifier(app_config.telegram, history, app_config.service.name)
    scheduler = CollectorScheduler(app_config, store, history, telegram)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(scheduler.run_forever())
        yield
        scheduler.stop()
        await task

    app = FastAPI(
        title="MystMon API",
        version=__version__,
        description="Dockerized Prometheus and SNMP monitoring bridge.",
        lifespan=lifespan,
    )
    app.state.config = app_config
    app.state.store = store
    app.state.history = history
    app.state.telegram = telegram
    app.state.scheduler = scheduler

    # Mount static files for UI
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Include UI router if enabled
    if app_config.ui.enabled:
        ui_router = create_ui_router(app_config, store, history, telegram, scheduler)
        app.include_router(ui_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/config")
    async def config_view() -> dict:
        return app_config.model_dump(mode="json")

    @app.get("/api/v1/readings")
    async def readings() -> list[dict]:
        return [reading.as_dict() for reading in store.all()]

    @app.get("/api/v1/snapshot")
    async def snapshot() -> dict:
        path = Path(app_config.outputs.latest_json_path)
        if not path.exists():
            await scheduler.collect_once()
        return json.loads(path.read_text(encoding="utf-8"))

    @app.post("/api/v1/collect")
    async def collect_now() -> dict[str, int]:
        return await scheduler.collect_once()

    @app.get("/api/v1/history/latest")
    async def history_latest() -> dict:
        if history is None:
            return {"ok": False, "reason": "history_disabled"}
        latest = history.latest_collection()
        return {"ok": latest is not None, "collection": latest}

    @app.get("/api/v1/history/overall")
    async def history_overall(limit: int = 100) -> dict:
        if history is None:
            return {"ok": False, "reason": "history_disabled"}
        return history.overall(limit=max(1, min(limit, 1000)))

    @app.get("/api/v1/history/delta")
    async def history_delta(hours: int = 24) -> dict:
        if history is None:
            return {"ok": False, "reason": "history_disabled", "hours": hours}
        return history.delta(hours=hours)

    @app.get("/api/v1/history/nodes")
    async def history_nodes(latest_only: bool = True, limit: int = 100) -> dict:
        if history is None:
            return {"ok": False, "reason": "history_disabled"}
        return history.nodes(latest_only=latest_only, limit=max(1, min(limit, 1000)))

    @app.get("/api/v1/history/nodes/{node}")
    async def history_node(node: str, limit: int = 100) -> dict:
        if history is None:
            return {"ok": False, "reason": "history_disabled", "node": node}
        return history.node(node=node, limit=max(1, min(limit, 1000)))

    @app.post("/api/v1/telegram/test")
    async def telegram_test() -> dict:
        return await telegram.send_test()

    @app.post("/api/v1/telegram/report")
    async def telegram_report(hours: int = 24) -> dict:
        return await telegram.send_report(hours=hours, force=True)

    @app.get("/metrics")
    async def metrics() -> Response:
        registry = CollectorRegistry()
        gauge = Gauge(
            "mystmon_reading",
            "Latest numeric reading collected by MystMon.",
            ["source_type", "source_name", "metric"],
            registry=registry,
        )
        node_running = Gauge("mystmon_node_running", "MYST container running state.", ["node"], registry=registry)
        node_restarts = Gauge("mystmon_node_restart_count", "MYST container restart count.", ["node"], registry=registry)
        node_uptime = Gauge("mystmon_node_uptime_seconds", "MYST container uptime.", ["node"], registry=registry)
        node_logs = Gauge("mystmon_node_log_events", "Recent MYST log event counts.", ["node", "event"], registry=registry)
        node_api = Gauge("mystmon_node_api_up", "MYST TequilAPI health probe state.", ["node"], registry=registry)
        node_api_endpoint = Gauge(
            "mystmon_node_api_endpoint_up",
            "MYST TequilAPI endpoint probe state.",
            ["node", "endpoint"],
            registry=registry,
        )
        node_api_metric = Gauge(
            "mystmon_node_api_metric",
            "Numeric metric collected from documented MYST TequilAPI endpoints.",
            ["node", "metric"],
            registry=registry,
        )
        node_api_info = Gauge(
            "mystmon_node_api_info",
            "String metadata collected from documented MYST TequilAPI endpoints.",
            ["node", "key", "value"],
            registry=registry,
        )
        portal_authenticated = Gauge(
            "mystmon_portal_authenticated",
            "MystNodes portal authentication state.",
            registry=registry,
        )
        portal_endpoint = Gauge(
            "mystmon_portal_endpoint_up",
            "MystNodes portal endpoint request state.",
            ["endpoint"],
            registry=registry,
        )
        portal_summary = Gauge(
            "mystmon_portal_summary",
            "MystNodes portal account summary values.",
            ["metric"],
            registry=registry,
        )
        portal_node_online = Gauge(
            "mystmon_portal_node_online",
            "MystNodes portal node online state.",
            ["node_id", "name", "identity", "local_ip"],
            registry=registry,
        )
        portal_node_quality = Gauge(
            "mystmon_portal_node_quality",
            "MystNodes portal node quality score.",
            ["node_id", "name", "identity", "local_ip"],
            registry=registry,
        )
        portal_node_earnings = Gauge(
            "mystmon_portal_node_earnings_total",
            "MystNodes portal per-node total earnings from node list.",
            ["node_id", "name", "identity", "local_ip"],
            registry=registry,
        )
        portal_node_uptime_24h = Gauge(
            "mystmon_portal_node_uptime_minutes_24h",
            "MystNodes portal node uptime minutes in the last 24 hours.",
            ["node_id", "name", "identity", "local_ip"],
            registry=registry,
        )
        portal_node_local_match = Gauge(
            "mystmon_portal_node_local_match",
            "Whether a MystNodes portal node was matched to a local Docker container by local IP.",
            ["node_id", "name", "local_ip", "container", "host"],
            registry=registry,
        )

        for reading in store.all():
            if isinstance(reading.value, (int, float)):
                gauge.labels(reading.source_type, reading.source_name, reading.metric).set(reading.value)

        snapshot_path = Path(app_config.outputs.latest_json_path)
        if snapshot_path.exists():
            snapshot_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
            for node in snapshot_data.get("nodes", []):
                name = node.get("name", "unknown")
                node_running.labels(name).set(1 if node.get("running") else 0)
                node_restarts.labels(name).set(node.get("restart_count", 0))
                node_uptime.labels(name).set(node.get("uptime_seconds", 0))
                for event, value in node.get("log_counts", {}).items():
                    node_logs.labels(name, event).set(value)
                api = node.get("api") or {}
                if api:
                    node_api.labels(name).set(1 if api.get("up") else 0)
                    for endpoint, endpoint_data in api.get("endpoints", {}).items():
                        node_api_endpoint.labels(name, endpoint).set(1 if endpoint_data.get("ok") else 0)
                    for metric, value in api.get("metrics", {}).items():
                        node_api_metric.labels(name, metric).set(value)
                    for key, value in api.get("labels", {}).items():
                        node_api_info.labels(name, key, str(value)).set(1)
            mystnodes = snapshot_data.get("mystnodes") or {}
            if mystnodes:
                portal_authenticated.set(1 if mystnodes.get("authenticated") else 0)
                for endpoint, endpoint_data in mystnodes.get("endpoints", {}).items():
                    portal_endpoint.labels(endpoint).set(1 if endpoint_data.get("ok") else 0)
                _set_portal_metrics(
                    mystnodes,
                    portal_summary,
                    portal_node_online,
                    portal_node_quality,
                    portal_node_earnings,
                    portal_node_uptime_24h,
                    portal_node_local_match,
                )

        return Response(
            content=generate_latest(registry),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return app


def _set_portal_metrics(
    mystnodes: dict,
    portal_summary: Gauge,
    portal_node_online: Gauge,
    portal_node_quality: Gauge,
    portal_node_earnings: Gauge,
    portal_node_uptime_24h: Gauge,
    portal_node_local_match: Gauge,
) -> None:
    endpoints = mystnodes.get("endpoints", {})
    me_data = (endpoints.get("me") or {}).get("data") or {}
    nodes_info = me_data.get("nodesInfo") or {}
    _set_numeric(portal_summary, "nodes_total", nodes_info.get("totalCount"))
    _set_numeric(portal_summary, "nodes_online", nodes_info.get("onlineCount"))

    total_earnings = ((endpoints.get("total_earnings") or {}).get("data") or {}).get("earningsTotal")
    total_transferred = ((endpoints.get("total_transferred") or {}).get("data") or {}).get("transferredTotal")
    _set_numeric(portal_summary, "earnings_total", total_earnings)
    _set_numeric(portal_summary, "transferred_total", total_transferred)

    node_details = (mystnodes.get("node_details") or {}).get("nodes", {})
    for node in _portal_nodes(mystnodes):
        node_id = str(node.get("id") or "")
        name = str(node.get("name") or "")
        identity = str(node.get("identity") or "")
        local_ip = str(node.get("localIp") or "")
        labels = (node_id, name, identity, local_ip)
        status = node.get("nodeStatus") or {}
        portal_node_online.labels(*labels).set(1 if status.get("online") else 0)
        _set_numeric_with_labels(portal_node_quality, labels, status.get("quality"))
        portal_node_earnings.labels(*labels).set(_sum_node_earnings(node.get("earnings")))
        detail = ((node_details.get(node_id) or {}).get("detail") or {}).get("data") or {}
        _set_numeric_with_labels(portal_node_uptime_24h, labels, detail.get("uptimeMinLast24H"))

    local_matches = mystnodes.get("local_matches") or {}
    for node in _portal_nodes(mystnodes):
        node_id = str(node.get("id") or "")
        name = str(node.get("name") or "")
        local_ip = str(node.get("localIp") or "")
        match = local_matches.get(node_id) or {}
        container = str(match.get("container_name") or match.get("name") or "")
        host = str(match.get("host") or "")
        portal_node_local_match.labels(node_id, name, local_ip, container, host).set(1 if match else 0)


def _portal_nodes(mystnodes: dict) -> list[dict]:
    nodes_data = ((mystnodes.get("endpoints") or {}).get("nodes") or {}).get("data") or {}
    nodes = nodes_data.get("nodes") if isinstance(nodes_data, dict) else None
    return [node for node in nodes or [] if isinstance(node, dict)]


def _set_numeric(gauge: Gauge, metric: str, value: object) -> None:
    try:
        gauge.labels(metric).set(float(value))
    except (TypeError, ValueError):
        return


def _set_numeric_with_labels(gauge: Gauge, labels: tuple[str, ...], value: object) -> None:
    try:
        gauge.labels(*labels).set(float(value))
    except (TypeError, ValueError):
        return


def _sum_node_earnings(earnings: object) -> float:
    if not isinstance(earnings, list):
        return 0.0
    total = 0.0
    for item in earnings:
        if not isinstance(item, dict):
            continue
        try:
            total += float(item.get("etherAmount") or 0)
        except (TypeError, ValueError):
            continue
    return total
