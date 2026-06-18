from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from mystmon import __version__
from mystmon.api import create_app
from mystmon.bootstrap import bootstrap_storage
from mystmon.config import MystMonConfig


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app(tmp_path):
    config = MystMonConfig.model_validate(
        {
            "service": {"data_dir": str(tmp_path)},
            "outputs": {
                "latest_json_path": str(tmp_path / "latest.json"),
                "snmp_extend_path": str(tmp_path / "snmp_extend.txt"),
            },
            "history": {
                "enabled": True,
                "db_path": str(tmp_path / "mystmon.db"),
            },
        }
    )
    config.ui.enabled = True
    bootstrap_storage(config.history.db_path, config.outputs.latest_json_path, config.outputs.snmp_extend_path)
    app = create_app(config)

    async def run_forever() -> None:
        return None

    app.state.scheduler.run_forever = run_forever
    return app


def _get(app, path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path, follow_redirects=False)

    return asyncio.run(request())


def test_ui_dashboard(app):
    response = _get(app, "/ui")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Dashboard" in response.text
    assert __version__ in response.text
    assert 'data-ui-path="/ui"' in response.text
    assert "/ui/static/js/utils.js" in response.text
    assert "/ui/static/js/api.js" in response.text
    assert "/ui/static/js/dashboard.js" in response.text


def test_ui_dashboard_polyfills_random_uuid_before_chartjs(app):
    response = _get(app, "/ui")

    assert "window.crypto.randomUUID" in response.text
    assert response.text.index("window.crypto.randomUUID") < response.text.index("chart.js@4.4.1")


def test_ui_static_assets_are_mounted_under_ui_path(app):
    mounted_paths = {route.path for route in app.routes}

    assert "/static" in mounted_paths
    assert "/ui/static" in mounted_paths


def test_ui_fleet(app):
    response = _get(app, "/ui/fleet")
    assert response.status_code == 200
    assert "Fleet Overview" in response.text


def test_ui_history(app):
    response = _get(app, "/ui/history")
    assert response.status_code == 200
    assert "History &amp; Trends" in response.text


def test_ui_settings(app):
    response = _get(app, "/ui/settings")
    assert response.status_code == 200
    assert "Settings" in response.text


def test_ui_api_config(app):
    response = _get(app, "/api/v1/ui/config")
    assert response.status_code == 200
    data = response.json()
    assert "auto_refresh_interval_seconds" in data
    assert "theme" in data


def test_ui_api_collectors_status(app):
    response = _get(app, "/api/v1/collectors/status")
    assert response.status_code == 200
    data = response.json()
    assert "collectors" in data
    assert data["collectors"]["myst"]["status"] == "pending"
    assert data["collectors"]["mystnodes"]["status"] == "disabled"
    assert data["collectors"]["prometheus"]["status"] == "disabled"
    assert data["collectors"]["snmp"]["status"] == "disabled"


def test_ui_api_collectors_status_uses_configured_sources(app, tmp_path):
    snapshot_path = tmp_path / "latest.json"
    config = MystMonConfig.model_validate(
        {
            "service": {"data_dir": str(tmp_path)},
            "outputs": {
                "latest_json_path": str(snapshot_path),
                "snmp_extend_path": str(tmp_path / "snmp_extend.txt"),
            },
            "history": {
                "enabled": True,
                "db_path": str(tmp_path / "mystmon.db"),
            },
            "mystnodes": {"enabled": False},
            "prometheus": {"enabled": True, "targets": []},
            "snmp": {"enabled": True, "targets": []},
        }
    )
    snapshot_path.write_text(
        json.dumps(
            {
                "generated_at": datetime(2026, 6, 6, 18, 48, tzinfo=UTC).isoformat(),
                "collection_counts": {"myst": 7, "mystnodes": 0, "prometheus": 0, "snmp": 0},
            }
        ),
        encoding="utf-8",
    )
    app = create_app(config)

    async def run_forever() -> None:
        return None

    app.state.scheduler.run_forever = run_forever
    response = _get(app, "/api/v1/collectors/status")
    data = response.json()

    assert data["collectors"]["myst"]["status"] == "ok"
    assert data["collectors"]["myst"]["nodes_collected"] == 7
    assert data["collectors"]["mystnodes"]["status"] == "disabled"
    assert data["collectors"]["prometheus"]["status"] == "disabled"
    assert data["collectors"]["snmp"]["status"] == "disabled"


def test_dashboard_preserves_unknown_portal_values_in_quick_nodes():
    source = (ROOT / "mystmon/static/js/dashboard.js").read_text(encoding="utf-8")

    assert "MystMonApi.historyOverall(48)" in source
    assert "pickMetric(current, ['quality_avg'])" in source
    assert "function isKnownNumber(value)" in source
    assert "return typeof value === 'number' && Number.isFinite(value);" in source
    assert "const points = Array.isArray(data) ? data.filter(isKnownNumber) : [];" in source
    assert "if (points.length === 0)" in source
    assert "deltaData.earnings_total" not in source
    assert "deltaData.quality" not in source


def test_dashboard_and_history_keep_missing_prior_health_unknown():
    dashboard = (ROOT / "mystmon/static/js/dashboard.js").read_text(encoding="utf-8")
    history = (ROOT / "mystmon/static/js/history.js").read_text(encoding="utf-8")

    assert "No prior data" in dashboard
    assert "No prior data" in history
    assert "pickMetric(current, ['online', 'running'])" in dashboard
    assert "pickMetric(prior, ['online', 'running'])" in dashboard
    assert "pickMetric(current, ['online', 'running'])" in history
    assert "pickMetric(prior, ['online', 'running'])" in history


def test_fleet_table_and_export_preserve_unknown_portal_values():
    source = (ROOT / "mystmon/static/js/fleet.js").read_text(encoding="utf-8")

    assert "api_nat_type" in source
    assert "api_public_ip" in source
    assert "api_location" in source
    assert "api_services_total" in source
    assert "api_services_running" in source
    assert "api_sessions_1d" in source
    assert "api_sessions_7d" in source
    assert "api_enabled" in source
    assert "api_schema_available" in source
    assert "Unknown" in source


def test_node_detail_uses_tequilapi_management_sections():
    source = (ROOT / "mystmon/static/js/node_detail.js").read_text(encoding="utf-8")
    template = (ROOT / "mystmon/templates/node_detail.html").read_text(encoding="utf-8")

    assert "TequilAPI Management" in template
    assert "TequilAPI Endpoint Diagnostics" in template
    assert "current?.provider_quality" in source
    assert "current?.api?.management?.health?.healthcheck?.version" in source
    assert "formatTequilLocation" in source
    assert "current?.nat_type" in source
    assert "current?.public_ip" in source


def test_dashboard_quick_nodes_show_tequilapi_columns():
    source = (ROOT / "mystmon/static/js/dashboard.js").read_text(encoding="utf-8")
    template = (ROOT / "mystmon/templates/dashboard.html").read_text(encoding="utf-8")

    assert "API" in template
    assert "NAT" in template
    assert "Public IP" in template
    assert "Services" in template
    assert "Sessions" in template
    assert "api_enabled" in source
    assert "api_nat_type" in source
    assert "api_public_ip" in source
    assert "api_services_running" in source
    assert "api_sessions_1d" in source


def test_ui_api_system_info(app):
    response = _get(app, "/api/v1/system/info")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "database" in data
    assert data["version"] == __version__


def test_ui_disabled(tmp_path):
    config = MystMonConfig.model_validate(
        {
            "service": {"data_dir": str(tmp_path)},
            "outputs": {
                "latest_json_path": str(tmp_path / "latest.json"),
                "snmp_extend_path": str(tmp_path / "snmp_extend.txt"),
            },
            "history": {
                "enabled": True,
                "db_path": str(tmp_path / "mystmon.db"),
            },
        }
    )
    config.ui.enabled = False
    app = create_app(config)
    
    async def run_forever() -> None:
        return None

    app.state.scheduler.run_forever = run_forever
    response = _get(app, "/ui")
    assert response.status_code == 404
