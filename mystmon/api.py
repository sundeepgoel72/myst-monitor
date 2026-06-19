from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Any

from fastapi import FastAPI, HTTPException, Response, Query
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CollectorRegistry, Gauge, generate_latest

from mystmon import __version__
from mystmon.config import MystMonConfig, load_config
from mystmon.history import HistoryStore
from mystmon.scheduler import CollectorScheduler
from mystmon.storage import ReadingStore
from mystmon.telegram import TelegramNotifier
from mystmon.ui import create_ui_router
from mystmon.alerting import create_default_alert_manager, Alert, AlertState

LOGGER = logging.getLogger(__name__)


def create_app(config: MystMonConfig | None = None) -> FastAPI:
    app_config = config or load_config()
    store = ReadingStore()
    history = HistoryStore(app_config.history.db_path) if app_config.history.enabled else None
    telegram = TelegramNotifier(app_config)
    alert_manager = create_default_alert_manager(app_config) if app_config.alerting.enabled else None
    scheduler = CollectorScheduler(app_config, store, history, telegram, alert_manager)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if os.getenv("MYSTMON_DISABLE_SCHEDULER") == "1":
            yield
            return
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
    app.state.alert_manager = alert_manager
    app.state.scheduler = scheduler

    # Mount static files for UI
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        if app_config.ui.enabled:
            ui_static_path = f"{app_config.ui.path.rstrip('/')}/static"
            if ui_static_path != "/static":
                app.mount(ui_static_path, StaticFiles(directory=str(static_dir)), name="ui-static")

    # Include UI router if enabled
    if app_config.ui.enabled:
        ui_router = create_ui_router(app_config, store, history, telegram, scheduler)
        app.include_router(ui_router)

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/health")
    async def health_legacy() -> dict[str, str]:
        """Legacy health endpoint for backward compatibility"""
        return {"status": "ok", "version": __version__}

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url=f"{app_config.ui.path.rstrip('/')}/", status_code=307)

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
            try:
                await app.state.scheduler.collect_once()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Collection failed: {e}") from e
            if not path.exists():
                raise HTTPException(status_code=404, detail="No snapshot available after collection")
        try:
            content = path.read_text(encoding="utf-8")
            if not content.strip():
                raise HTTPException(status_code=404, detail="Snapshot file is empty")
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"Invalid JSON in snapshot: {e}") from e
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read snapshot: {e}") from e

    @app.post("/api/v1/collect")
    async def collect_now() -> dict[str, int]:
        return await app.state.scheduler.collect_once()

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

    @app.get("/api/v1/alerts")
    async def get_alerts() -> list[dict]:
        if alert_manager is None:
            return []
        return [alert.__dict__ for alert in alert_manager.get_active_alerts()]

    @app.get("/api/v1/alerts/history")
    async def get_alerts_history(limit: int = Query(100, ge=1, le=1000)) -> list[dict]:
        if alert_manager is None:
            return []
        return [alert.__dict__ for alert in alert_manager.get_alert_history(limit=limit)]

    @app.post("/api/v1/alerts/acknowledge")
    async def acknowledge_alert(alert_id: str, user: str = "system") -> dict:
        if alert_manager is None:
            raise HTTPException(status_code=400, detail="Alerting is not enabled")
        if alert_manager.acknowledge_alert(alert_id, user):
            return {"status": "acknowledged", "alert_id": alert_id}
        else:
            raise HTTPException(status_code=404, detail="Alert not found")

    @app.get("/api/v1/alerts/evaluate")
    async def evaluate_alerts() -> list[dict]:
        if alert_manager is None:
            return []
        alerts = alert_manager.evaluate_all_readings(store)
        return [alert.__dict__ for alert in alerts]

    @app.get("/api/v1/metrics")
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

        # New TequilAPI metrics
        node_api_auth = Gauge("mystmon_node_api_auth", "MYST TequilAPI authentication state.", ["node"], registry=registry)
        node_api_schema = Gauge("mystmon_node_api_schema_available", "MYST TequilAPI schema discovery success.", ["node"], registry=registry)
        node_sessions_active = Gauge("mystmon_node_sessions_active", "Active sessions count.", ["node"], registry=registry)
        node_sessions_count = Gauge("mystmon_node_sessions_count", "Session count by range.", ["node", "range"], registry=registry)
        node_services_total = Gauge("mystmon_node_services_total", "Total services count.", ["node"], registry=registry)
        node_services_running = Gauge("mystmon_node_services_running", "Running services count.", ["node"], registry=registry)
        node_provider_quality = Gauge("mystmon_node_provider_quality", "Provider quality score.", ["node"], registry=registry)
        node_provider_transferred = Gauge("mystmon_node_provider_transferred_data", "Provider transferred data.", ["node"], registry=registry)
        node_provider_service_earnings = Gauge("mystmon_node_provider_service_earnings", "Provider service earnings.", ["node"], registry=registry)
        node_payments_balance = Gauge("mystmon_node_payments_balance", "Payments balance.", ["node"], registry=registry)
        node_nat_type = Gauge("mystmon_node_nat_type", "NAT type.", ["node", "type"], registry=registry)

        # Multi-account metrics
        portal_account_authenticated = Gauge(
            "mystmon_portal_account_authenticated",
            "MystNodes portal account authentication state.",
            ["account"],
            registry=registry,
        )
        portal_account_nodes_total = Gauge(
            "mystmon_portal_account_nodes_total",
            "MystNodes portal account total nodes.",
            ["account"],
            registry=registry,
        )
        portal_account_nodes_online = Gauge(
            "mystmon_portal_account_nodes_online",
            "MystNodes portal account online nodes.",
            ["account"],
            registry=registry,
        )
        portal_account_earnings_total = Gauge(
            "mystmon_portal_account_earnings_total",
            "MystNodes portal account total earnings.",
            ["account"],
            registry=registry,
        )

        # System metrics
        system_cpu_percent = Gauge("mystmon_system_cpu_percent", "System CPU usage percentage.", registry=registry)
        system_memory_percent = Gauge("mystmon_system_memory_percent", "System memory usage percentage.", registry=registry)
        system_disk_percent = Gauge("mystmon_system_disk_percent", "System disk usage percentage.", ["mountpoint"], registry=registry)
        system_network_bytes_sent = Gauge("mystmon_system_network_bytes_sent", "System network bytes sent.", registry=registry)
        system_network_bytes_recv = Gauge("mystmon_system_network_bytes_recv", "System network bytes received.", registry=registry)
        system_uptime_seconds = Gauge("mystmon_system_uptime_seconds", "System uptime in seconds.", registry=registry)

        # Alert metrics
        alert_gauge = Gauge(
            "mystmon_alerts_active",
            "Number of active alerts by severity.",
            ["severity"],
            registry=registry,
        )
        if alert_manager is not None:
            active_alerts = alert_manager.get_active_alerts()
            for alert in active_alerts:
                alert_gauge.labels(alert.severity.value).inc()

        for reading in store.all():
            if isinstance(reading.value, (int, float)):
                gauge.labels(reading.source_type, reading.source_name, reading.metric).set(reading.value)

        # Add system metrics to Prometheus output
        for reading in store.by_source_type("system"):
            if isinstance(reading.value, (int, float)):
                if reading.metric_name == "cpu_percent":
                    system_cpu_percent.set(reading.value)
                elif reading.metric_name == "memory_virtual_percent":
                    system_memory_percent.set(reading.value)
                elif reading.metric_name == "disk_percent":
                    mountpoint = reading.labels.get("mountpoint", "unknown")
                    system_disk_percent.labels(mountpoint).set(reading.value)
                elif reading.metric_name == "network_io_bytes_sent":
                    system_network_bytes_sent.set(reading.value)
                elif reading.metric_name == "network_io_bytes_recv":
                    system_network_bytes_recv.set(reading.value)
                elif reading.metric_name == "system_uptime_seconds":
                    system_uptime_seconds.set(reading.value)

        snapshot_path = Path(app_config.outputs.latest_json_path)
        if snapshot_path.exists():
            try:
                content = snapshot_path.read_text(encoding="utf-8")
                if content.strip():
                    snapshot_data = json.loads(content)
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
                            node_api_auth.labels(name).set(1 if api.get("auth") else 0)
                            node_api_schema.labels(name).set(1 if api.get("schema_available") else 0)
                            management = api.get("management") or {}
                            sessions = management.get("sessions") or {}
                            provider = management.get("provider") or {}
                            payments = management.get("payments") or {}
                            nat = management.get("nat") or {}
                            _set_numeric_or_none(node_sessions_active, name, node.get("sessions_active") or _nested_metric(sessions, ("sessions", "count")) or _nested_metric(sessions, ("sessions", "active")))
                            _set_numeric_or_none(node_services_total, name, node.get("services_count"))
                            _set_numeric_or_none(node_services_running, name, node.get("services_running"))
                            _set_numeric_or_none(node_provider_quality, name, node.get("provider_quality") or _nested_metric(provider, ("provider_stats", "quality")) or _nested_metric(provider, ("quality",)))
                            _set_numeric_or_none(node_provider_transferred, name, node.get("provider_transferred_data"))
                            _set_numeric_or_none(node_provider_service_earnings, name, node.get("provider_service_earnings"))
                            _set_numeric_or_none(node_payments_balance, name, node.get("payments_balance") or _nested_metric(payments, ("payments_balance", "balance")))
                            sessions_1d = node.get("sessions_1d") or _nested_metric(sessions, ("sessions", "count"))
                            sessions_7d = node.get("sessions_7d") or _nested_metric(sessions, ("sessions", "count"))
                            if sessions_1d is not None:
                                _set_numeric_with_range(node_sessions_count, name, "1d", sessions_1d)
                            if sessions_7d is not None:
                                _set_numeric_with_range(node_sessions_count, name, "7d", sessions_7d)
                            nat_type = node.get("nat_type") or nat.get("nat_type") or nat.get("type")
                            if nat_type:
                                node_nat_type.labels(name, str(nat_type)).set(1)
                            for endpoint, endpoint_data in api.get("endpoints", {}).items():
                                node_api_endpoint.labels(name, endpoint).set(1 if endpoint_data.get("ok") else 0)
                            for metric, value in api.get("metrics", {}).items():
                                if isinstance(value, (int, float)):
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
                        
                        # Handle multi-account metrics
                        accounts = mystnodes.get("accounts", [])
                        for account in accounts:
                            account_name = account.get("name", "unknown")
                            portal_account_authenticated.labels(account_name).set(1 if account.get("authenticated") else 0)
                            
                            # Account summary metrics
                            endpoints = account.get("endpoints", {})
                            me_data = (endpoints.get("me") or {}).get("data") or {}
                            nodes_info = me_data.get("nodesInfo") or {}
                            portal_account_nodes_total.labels(account_name).set(nodes_info.get("totalCount", 0))
                            portal_account_nodes_online.labels(account_name).set(nodes_info.get("onlineCount", 0))
                            
                            total_earnings = ((endpoints.get("total_earnings") or {}).get("data") or {}).get("earningsTotal", 0)
                            portal_account_earnings_total.labels(account_name).set(total_earnings)
            except Exception:
                LOGGER.warning("Error processing snapshot for metrics", exc_info=True)

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
    # Handle multi-account structure
    accounts = mystnodes.get("accounts", [])
    if accounts:
        nodes = []
        for account in accounts:
            account_nodes = _portal_nodes_single_account(account)
            # Add account provenance to nodes
            for node in account_nodes:
                node["account"] = account.get("name", "unknown")
            nodes.extend(account_nodes)
        return nodes
    else:
        # Handle single account structure for backward compatibility
        return _portal_nodes_single_account(mystnodes)


def _portal_nodes_single_account(account_data: dict) -> list[dict]:
    nodes_data = ((account_data.get("endpoints") or {}).get("nodes") or {}).get("data") or {}
    nodes = nodes_data.get("nodes") if isinstance(nodes_data, dict) else None
    return [node for node in nodes or [] if isinstance(node, dict)]


def _set_numeric(gauge: Gauge, metric: str, value: object) -> None:
    try:
        if value is not None:
            gauge.labels(metric).set(float(value))
    except (TypeError, ValueError):
        return


def _set_numeric_with_labels(gauge: Gauge, labels: tuple[str, ...], value: object) -> None:
    try:
        if value is not None:
            gauge.labels(*labels).set(float(value))
    except (TypeError, ValueError):
        return


def _set_numeric_or_none(gauge: Gauge, node: str, value: object) -> None:
    try:
        if value is not None:
            gauge.labels(node).set(float(value))
    except (TypeError, ValueError):
        return


def _set_numeric_with_range(gauge: Gauge, node: str, range_value: str, value: object) -> None:
    try:
        if value is not None:
            gauge.labels(node, range_value).set(float(value))
    except (TypeError, ValueError):
        return


def _nested_metric(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


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
