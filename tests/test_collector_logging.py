from __future__ import annotations

import asyncio
import logging

import httpx
import pytest

from mystmon.collectors.prometheus import collect_prometheus
from mystmon.collectors.snmp import collect_snmp
from mystmon.config import PrometheusTarget, SnmpTarget


class _PrometheusClient:
    def __init__(self, response: httpx.Response | None = None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        if self.exc is not None:
            raise self.exc
        assert self.response is not None
        return self.response


def test_collect_prometheus_logs_http_error(monkeypatch, caplog) -> None:
    request = httpx.Request("GET", "http://example.invalid/metrics")
    response = httpx.Response(500, request=request, text="boom")

    monkeypatch.setattr("mystmon.collectors.prometheus.httpx.AsyncClient", lambda timeout: _PrometheusClient(response=response))

    caplog.set_level(logging.ERROR)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(collect_prometheus(PrometheusTarget(name="demo", url="http://example.invalid/metrics"), 3))

    assert "Prometheus collection failed" in caplog.text
    assert "target=demo" in caplog.text
    assert "reason=http_error" in caplog.text


def test_collect_prometheus_logs_parse_error(monkeypatch, caplog) -> None:
    request = httpx.Request("GET", "http://example.invalid/metrics")
    response = httpx.Response(200, request=request, text="not a prometheus payload")

    monkeypatch.setattr("mystmon.collectors.prometheus.httpx.AsyncClient", lambda timeout: _PrometheusClient(response=response))

    caplog.set_level(logging.ERROR)
    readings = asyncio.run(collect_prometheus(PrometheusTarget(name="demo", url="http://example.invalid/metrics"), 3))

    assert readings == []
    assert "Prometheus collection failed" not in caplog.text


def test_collect_snmp_logs_transport_failure(monkeypatch, caplog) -> None:
    async def fake_create(*args, **kwargs):
        raise TimeoutError("snmp timeout")

    monkeypatch.setattr("mystmon.collectors.snmp.UdpTransportTarget.create", fake_create)

    caplog.set_level(logging.ERROR)
    with pytest.raises(TimeoutError):
        asyncio.run(
            collect_snmp(
                SnmpTarget(name="router", host="192.0.2.1", oids={"uptime": "1.3.6.1.2.1.1.3.0"}),
                "public",
                2,
            )
        )

    assert "SNMP collection failed" in caplog.text
    assert "target=router" in caplog.text
    assert "reason=transport_error" in caplog.text


def test_collect_snmp_logs_error_indication(monkeypatch, caplog) -> None:
    class _ErrorIndication(str):
        pass

    async def fake_create(*args, **kwargs):
        return object()

    async def fake_get_cmd(*args, **kwargs):
        return (_ErrorIndication("no response"), None, None, [])

    monkeypatch.setattr("mystmon.collectors.snmp.UdpTransportTarget.create", fake_create)
    monkeypatch.setattr("mystmon.collectors.snmp.get_cmd", fake_get_cmd)

    caplog.set_level(logging.ERROR)
    with pytest.raises(RuntimeError, match="no response"):
        asyncio.run(
            collect_snmp(
                SnmpTarget(name="router", host="192.0.2.1", oids={"uptime": "1.3.6.1.2.1.1.3.0"}),
                "public",
                2,
            )
        )

    assert "reason=error_indication" in caplog.text
