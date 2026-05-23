from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Response
from prometheus_client import CollectorRegistry, Gauge, generate_latest

from mystmon import __version__
from mystmon.config import MystMonConfig, load_config
from mystmon.scheduler import CollectorScheduler
from mystmon.storage import ReadingStore


def create_app(config: MystMonConfig | None = None) -> FastAPI:
    app_config = config or load_config()
    store = ReadingStore()
    scheduler = CollectorScheduler(app_config, store)

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
    app.state.scheduler = scheduler

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

        return Response(
            content=generate_latest(registry),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return app
