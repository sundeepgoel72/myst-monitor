from __future__ import annotations

import asyncio

import httpx

from mystmon.collectors.myst import collect_myst
from mystmon.config import MystCollectorConfig, MystContainerConfig, TequilApiEndpointConfig


def test_collect_myst_uses_configured_local_runtime_hosts(monkeypatch) -> None:
    captured: list[tuple[str, str]] = []

    async def fake_get(self: httpx.AsyncClient, path: str, *args, **kwargs):
        captured.append((str(self.base_url), path))

        class Response:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self):
                if path == "/identities":
                    return {"identities": [{"id": "0x123"}]}
                return {"uptime": "1h"}

        return Response()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    config = MystCollectorConfig(
        enabled=True,
        api_probe_enabled=True,
        api_endpoints=[
            TequilApiEndpointConfig(
                name="identities",
                path="/identities",
                metric_prefix="identities",
                category="identities",
            )
        ],
        containers=[
            MystContainerConfig(
                name="myst.12.x",
                host="192.168.12.71",
                tequilapi_port=4050,
            )
        ],
        remote_hosts=[],
    )

    readings = asyncio.run(collect_myst(config, 10))

    assert readings
    assert ("http://192.168.12.71:4050", "/healthcheck") in captured
    assert ("http://192.168.12.71:4050", "/identities") in captured
    assert any(reading.metric_name == "api_up" and reading.value == 1.0 for reading in readings)
    assert any(reading.raw_data.get("host") == "192.168.12.71" for reading in readings if reading.raw_data)
