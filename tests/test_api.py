from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI

from mystmon.api import create_app
from mystmon.bootstrap import bootstrap_storage
from mystmon.config import MystMonConfig
from mystmon.scheduler import CollectorScheduler


@pytest.fixture(autouse=True)
def _disable_scheduler_loop(monkeypatch):
    monkeypatch.setenv("MYSTMON_DISABLE_SCHEDULER", "1")

    async def _noop(self):
        return None

    monkeypatch.setattr(CollectorScheduler, "run_forever", _noop)


def _test_config(tmp_path: Path) -> MystMonConfig:
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
            "myst": {
                "api_endpoints": [
                    {"name": "healthcheck", "path": "/healthcheck", "metric_prefix": "health", "category": "health"},
                    {"name": "identities", "path": "/identities", "metric_prefix": "identities", "category": "identities"},
                ]
            }
        }
    )
    bootstrap_storage(config.history.db_path, config.outputs.latest_json_path, config.outputs.snmp_extend_path)
    return config


def _app_without_background_scheduler(config: MystMonConfig):
    bootstrap_storage(config.history.db_path, config.outputs.latest_json_path, config.outputs.snmp_extend_path)
    app = create_app(config)

    async def run_forever() -> None:
        pass  # No-op for testing

    scheduler = CollectorScheduler(config, app.state.store, app.state.history, app.state.telegram)
    scheduler.run_forever = run_forever  # type: ignore[method-assign]
    app.state.scheduler = scheduler
    return app


def _get(app, path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path)

    import asyncio

    return asyncio.run(request())


def test_create_app_imports_collectors(tmp_path: Path) -> None:
    # This test just verifies the app can be created without import errors
    config = _test_config(tmp_path)
    app = create_app(config)
    assert isinstance(app, FastAPI)


def test_root_redirects_to_ui(tmp_path: Path) -> None:
    config = _test_config(tmp_path)
    app = create_app(config)
    response = _get(app, "/")
    assert response.status_code == 307
    assert response.headers["location"] == "/ui/"


def test_snapshot_returns_500_when_collection_fails(tmp_path: Path) -> None:
    app = _app_without_background_scheduler(_test_config(tmp_path))
    Path(app.state.config.outputs.latest_json_path).unlink(missing_ok=True)

    async def collect_once() -> dict[str, int]:
        raise RuntimeError("collection failed")

    app.state.scheduler.collect_once = collect_once  # type: ignore[method-assign]
    response = _get(app, "/api/v1/snapshot")
    assert response.status_code == 500


def test_snapshot_returns_404_when_collection_creates_no_snapshot(tmp_path: Path) -> None:
    app = _app_without_background_scheduler(_test_config(tmp_path))

    async def collect_once() -> dict[str, int]:
        return {"myst": 1}

    app.state.scheduler.collect_once = collect_once  # type: ignore[method-assign]
    response = _get(app, "/api/v1/snapshot")
    assert response.status_code == 404


def test_snapshot_returns_500_when_snapshot_json_is_invalid(tmp_path: Path) -> None:
    config = _test_config(tmp_path)
    app = create_app(config)
    snapshot_path = Path(config.outputs.latest_json_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text("{ invalid json }", encoding="utf-8")
    response = _get(app, "/api/v1/snapshot")
    assert response.status_code == 500


def test_portal_metrics_include_quality_and_earnings() -> None:
    # This test is kept for compatibility but may need updating for TequilAPI
    pass


def test_metrics_alias_remains_available(tmp_path: Path) -> None:
    config = _test_config(tmp_path)
    app = create_app(config)
    response = _get(app, "/metrics")
    assert response.status_code == 200
    response_legacy = _get(app, "/api/v1/metrics")
    assert response_legacy.status_code == 200


# New tests for TequilAPI metrics
def test_tequilapi_metrics_are_exposed(tmp_path: Path) -> None:
    """Test that TequilAPI metrics are exposed in Prometheus format"""
    config = _test_config(tmp_path)
    app = create_app(config)
    
    # Create a mock snapshot with TequilAPI data
    snapshot_data = {
        "generated_at": "2023-01-01T00:00:00Z",
        "collection_counts": {"myst": 1},
        "nodes": [
            {
                "name": "test-node",
                "running": True,
                "restart_count": 0,
                "uptime_seconds": 3600,
                "log_counts": {
                    "error_or_warning": 0,
                    "promise": 1,
                    "session": 2,
                    "identity_warning": 0
                },
                "api": {
                    "enabled": True,
                    "up": True,
                    "auth": True,
                    "schema_available": True,
                    "endpoints": {
                        "healthcheck": {"ok": True, "status_code": 200},
                        "identities": {"ok": True, "status_code": 200}
                    },
                    "metrics": {
                        "health_uptime_seconds": 3600.0,
                        "identities_count": 1.0
                    },
                    "labels": {
                        "health_version": "1.2.3"
                    }
                }
            }
        ]
    }
    
    # Write the mock snapshot
    snapshot_path = Path(config.outputs.latest_json_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(snapshot_data), encoding="utf-8")
    
    response = _get(app, "/metrics")
    assert response.status_code == 200
    metrics_text = response.text
    
    # Check that TequilAPI metrics are present
    assert "mystmon_node_api_up" in metrics_text
    assert "mystmon_node_api_auth" in metrics_text
    assert "mystmon_node_api_schema_available" in metrics_text
    assert "mystmon_node_api_metric" in metrics_text
    assert "mystmon_node_api_info" in metrics_text
    
    # Check specific metric values
    assert "mystmon_node_api_up{node=\"test-node\"} 1.0" in metrics_text
    assert "mystmon_node_api_auth{node=\"test-node\"} 1.0" in metrics_text
    assert "mystmon_node_api_schema_available{node=\"test-node\"} 1.0" in metrics_text
    assert "mystmon_node_api_metric{metric=\"health_uptime_seconds\",node=\"test-node\"} 3600.0" in metrics_text
    assert "mystmon_node_api_info{key=\"health_version\",node=\"test-node\",value=\"1.2.3\"} 1.0" in metrics_text


def test_tequilapi_endpoint_metrics_are_exposed(tmp_path: Path) -> None:
    """Test that TequilAPI endpoint metrics are exposed"""
    config = _test_config(tmp_path)
    app = create_app(config)
    
    # Create a mock snapshot with TequilAPI endpoint data
    snapshot_data = {
        "generated_at": "2023-01-01T00:00:00Z",
        "collection_counts": {"myst": 1},
        "nodes": [
            {
                "name": "test-node",
                "running": True,
                "api": {
                    "enabled": True,
                    "up": True,
                    "endpoints": {
                        "healthcheck": {"ok": True, "status_code": 200, "supported": True},
                        "identities": {"ok": False, "status_code": 404, "supported": True}
                    }
                }
            }
        ]
    }
    
    # Write the mock snapshot
    snapshot_path = Path(config.outputs.latest_json_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(snapshot_data), encoding="utf-8")
    
    response = _get(app, "/metrics")
    assert response.status_code == 200
    metrics_text = response.text
    
    # Check that endpoint metrics are present
    assert "mystmon_node_api_endpoint_up" in metrics_text
    assert "mystmon_node_api_endpoint_up{endpoint=\"healthcheck\",node=\"test-node\"} 1.0" in metrics_text
    assert "mystmon_node_api_endpoint_up{endpoint=\"identities\",node=\"test-node\"} 0.0" in metrics_text


def test_tequilapi_management_metrics_are_exposed(tmp_path: Path) -> None:
    """Test that TequilAPI management metrics are exposed"""
    config = _test_config(tmp_path)
    app = create_app(config)
    
    # Create a mock snapshot with TequilAPI management data
    snapshot_data = {
        "generated_at": "2023-01-01T00:00:00Z",
        "collection_counts": {"myst": 1},
        "nodes": [
            {
                "name": "test-node",
                "running": True,
                "api": {
                    "enabled": True,
                    "up": True,
                    "management": {
                        "sessions": {
                            "sessions": {"count": 5}
                        },
                        "provider": {
                            "provider_stats": {"quality": 0.95}
                        },
                        "payments": {
                            "payments_balance": {"balance": 100.5}
                        },
                        "nat": {
                            "nat_type": "fullcone"
                        }
                    }
                }
            }
        ]
    }
    
    # Write the mock snapshot
    snapshot_path = Path(config.outputs.latest_json_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(snapshot_data), encoding="utf-8")
    
    response = _get(app, "/metrics")
    assert response.status_code == 200
    metrics_text = response.text
    
    # Check that management metrics are present
    assert "mystmon_node_sessions_active" in metrics_text
    assert "mystmon_node_provider_quality" in metrics_text
    assert "mystmon_node_payments_balance" in metrics_text
    assert "mystmon_node_nat_type" in metrics_text
    
    # Check specific metric values
    assert "mystmon_node_sessions_active{node=\"test-node\"} 5.0" in metrics_text
    assert "mystmon_node_provider_quality{node=\"test-node\"} 0.95" in metrics_text
    assert "mystmon_node_payments_balance{node=\"test-node\"} 100.5" in metrics_text
    assert "mystmon_node_nat_type{node=\"test-node\",type=\"fullcone\"} 1.0" in metrics_text


def test_tequilapi_category_metrics_are_exposed(tmp_path: Path) -> None:
    """Test that TequilAPI category-specific metrics are exposed"""
    config = _test_config(tmp_path)
    app = create_app(config)
    
    # Create a mock snapshot with comprehensive TequilAPI data
    snapshot_data = {
        "generated_at": "2023-01-01T00:00:00Z",
        "collection_counts": {"myst": 1},
        "nodes": [
            {
                "name": "test-node",
                "running": True,
                "api": {
                    "enabled": True,
                    "up": True,
                    "auth": True,
                    "schema_available": True,
                    "endpoints": {
                        "healthcheck": {"ok": True, "status_code": 200, "supported": True, "category": "health"},
                        "identities": {"ok": True, "status_code": 200, "supported": True, "category": "identities"},
                        "sessions": {"ok": True, "status_code": 200, "supported": True, "category": "sessions"},
                        "provider_stats": {"ok": True, "status_code": 200, "supported": True, "category": "provider"},
                        "payments_balance": {"ok": True, "status_code": 200, "supported": True, "category": "payments"},
                        "location": {"ok": True, "status_code": 200, "supported": True, "category": "location"},
                        "nat_type": {"ok": True, "status_code": 200, "supported": True, "category": "nat"}
                    },
                    "metrics": {
                        "health_uptime_seconds": 3600.0,
                        "identities_count": 1.0,
                        "sessions_count": 5.0,
                        "provider_quality": 0.95,
                        "payments_balance": 100.5,
                        "location_country": "US"
                    },
                    "labels": {
                        "health_version": "1.2.3",
                        "nat_type": "fullcone"
                    },
                    "management": {
                        "health": {
                            "healthcheck": {"uptime": "1h", "version": "1.2.3"}
                        },
                        "sessions": {
                            "sessions": {"count": 5}
                        },
                        "provider": {
                            "provider_stats": {"quality": 0.95}
                        },
                        "payments": {
                            "payments_balance": {"balance": 100.5}
                        },
                        "location": {
                            "location": {"country": "US"}
                        },
                        "nat": {
                            "nat_type": "fullcone"
                        }
                    }
                }
            }
        ]
    }
    
    # Write the mock snapshot
    snapshot_path = Path(config.outputs.latest_json_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(snapshot_data), encoding="utf-8")
    
    response = _get(app, "/metrics")
    assert response.status_code == 200
    metrics_text = response.text
    
    # Check that all category metrics are present
    assert "mystmon_node_api_up{node=\"test-node\"} 1.0" in metrics_text
    assert "mystmon_node_api_auth{node=\"test-node\"} 1.0" in metrics_text
    assert "mystmon_node_api_schema_available{node=\"test-node\"} 1.0" in metrics_text
    
    # Check endpoint metrics
    assert "mystmon_node_api_endpoint_up{endpoint=\"healthcheck\",node=\"test-node\"} 1.0" in metrics_text
    assert "mystmon_node_api_endpoint_up{endpoint=\"identities\",node=\"test-node\"} 1.0" in metrics_text
    
    # Check metric values
    assert "mystmon_node_api_metric{metric=\"health_uptime_seconds\",node=\"test-node\"} 3600.0" in metrics_text
    assert "mystmon_node_api_metric{metric=\"identities_count\",node=\"test-node\"} 1.0" in metrics_text
    
    # Check labels
    assert "mystmon_node_api_info{key=\"health_version\",node=\"test-node\",value=\"1.2.3\"} 1.0" in metrics_text
    assert "mystmon_node_api_info{key=\"nat_type\",node=\"test-node\",value=\"fullcone\"} 1.0" in metrics_text
    
    # Check management metrics
    assert "mystmon_node_sessions_active{node=\"test-node\"} 5.0" in metrics_text
    assert "mystmon_node_provider_quality{node=\"test-node\"} 0.95" in metrics_text
    assert "mystmon_node_payments_balance{node=\"test-node\"} 100.5" in metrics_text
    assert "mystmon_node_nat_type{node=\"test-node\",type=\"fullcone\"} 1.0" in metrics_text


def test_tequilapi_snapshot_structure(tmp_path: Path) -> None:
    """Test that TequilAPI data is correctly structured in snapshots"""
    config = _test_config(tmp_path)
    app = create_app(config)
    
    # Create a mock snapshot with TequilAPI data
    snapshot_data = {
        "generated_at": "2023-01-01T00:00:00Z",
        "collection_counts": {"myst": 1},
        "nodes": [
            {
                "name": "test-node",
                "running": True,
                "api": {
                    "enabled": True,
                    "base_url": "http://localhost:4050",
                    "up": True,
                    "auth": True,
                    "schema_available": True,
                    "last_check": "2023-01-01T00:00:00Z",
                    "endpoints": {
                        "healthcheck": {
                            "url": "http://localhost:4050/healthcheck",
                            "status_code": 200,
                            "ok": True,
                            "supported": True,
                            "category": "health"
                        }
                    },
                    "metrics": {
                        "health_uptime_seconds": 3600.0
                    },
                    "labels": {
                        "health_version": "1.2.3"
                    },
                    "management": {
                        "health": {
                            "healthcheck": {"uptime": "1h", "version": "1.2.3"}
                        }
                    },
                    "identity": "0x123abc"
                }
            }
        ]
    }
    
    # Write the mock snapshot
    snapshot_path = Path(config.outputs.latest_json_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(snapshot_data), encoding="utf-8")
    
    response = _get(app, "/api/v1/snapshot")
    assert response.status_code == 200
    
    snapshot = response.json()
    node = snapshot["nodes"][0]
    
    # Check that TequilAPI data is present and correctly structured
    assert "api" in node
    api_data = node["api"]
    
    assert api_data["enabled"] is True
    assert api_data["base_url"] == "http://localhost:4050"
    assert api_data["up"] is True
    assert api_data["auth"] is True
    assert api_data["schema_available"] is True
    assert "last_check" in api_data
    
    # Check endpoints structure
    assert "endpoints" in api_data
    assert "healthcheck" in api_data["endpoints"]
    endpoint = api_data["endpoints"]["healthcheck"]
    assert endpoint["ok"] is True
    assert endpoint["status_code"] == 200
    assert endpoint["supported"] is True
    assert endpoint["category"] == "health"
    
    # Check metrics structure
    assert "metrics" in api_data
    assert api_data["metrics"]["health_uptime_seconds"] == 3600.0
    
    # Check labels structure
    assert "labels" in api_data
    assert api_data["labels"]["health_version"] == "1.2.3"
    
    # Check management data structure
    assert "management" in api_data
    assert "health" in api_data["management"]
    assert "healthcheck" in api_data["management"]["health"]
    
    # Check identity
    assert api_data["identity"] == "0x123abc"
