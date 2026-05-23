from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
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

        for reading in store.all():
            if isinstance(reading.value, (int, float)):
                gauge.labels(reading.source_type, reading.source_name, reading.metric).set(reading.value)

        return Response(
            content=generate_latest(registry),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return app

