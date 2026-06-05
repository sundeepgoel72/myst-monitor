from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mystmon.api import create_app
from mystmon.config import MystMonConfig


@pytest.fixture
def app():
    config = MystMonConfig()
    config.ui.enabled = True
    return create_app(config)


@pytest.fixture
def client(app):
    return TestClient(app)


def test_ui_dashboard(client):
    response = client.get("/ui")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "MystMon Dashboard" in response.text


def test_ui_fleet(client):
    response = client.get("/ui/fleet")
    assert response.status_code == 200
    assert "Fleet Overview" in response.text


def test_ui_history(client):
    response = client.get("/ui/history")
    assert response.status_code == 200
    assert "History & Trends" in response.text


def test_ui_settings(client):
    response = client.get("/ui/settings")
    assert response.status_code == 200
    assert "Settings" in response.text


def test_ui_api_config(client):
    response = client.get("/api/v1/ui/config")
    assert response.status_code == 200
    data = response.json()
    assert "auto_refresh_interval_seconds" in data
    assert "theme" in data


def test_ui_api_collectors_status(client):
    response = client.get("/api/v1/collectors/status")
    assert response.status_code == 200
    data = response.json()
    assert "collectors" in data


def test_ui_api_system_info(client):
    response = client.get("/api/v1/system/info")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "database" in data


def test_ui_disabled(client):
    # Create app with UI disabled
    from mystmon.config import MystMonConfig
    from mystmon.api import create_app
    
    config = MystMonConfig()
    config.ui.enabled = False
    app = create_app(config)
    test_client = TestClient(app)
    
    response = test_client.get("/ui")
    assert response.status_code == 404
