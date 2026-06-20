from __future__ import annotations

import os

import pytest
import requests

from mystmon import __version__


@pytest.mark.integration
def test_major_release_live_validation_matches_current_version() -> None:
    base_url = os.getenv("MYSTMON_RELEASE_VALIDATION_URL")
    expected_nodes = int(os.getenv("MYSTMON_EXPECTED_NODE_COUNT", "8"))
    if not base_url:
        pytest.skip("Set MYSTMON_RELEASE_VALIDATION_URL to run the live release validation test")

    health = requests.get(f"{base_url.rstrip('/')}/health", timeout=20)
    health.raise_for_status()
    health_data = health.json()
    assert health_data["status"] == "ok"
    assert health_data["version"] == __version__

    snapshot_resp = requests.get(f"{base_url.rstrip('/')}/api/v1/snapshot", timeout=60)
    snapshot_resp.raise_for_status()
    snapshot = snapshot_resp.json()

    assert snapshot["collection_counts"]["myst"] == expected_nodes
    assert len(snapshot["nodes"]) == expected_nodes
    portal = snapshot.get("mystnodes") or {}
    if portal:
        assert "authenticated" in portal
        assert "endpoints" in portal
        assert "wallet_address" not in portal
        assert portal.get("wallet_address_hint") is not None

    metrics_resp = requests.get(f"{base_url.rstrip('/')}/metrics", timeout=20)
    metrics_resp.raise_for_status()
    metrics = metrics_resp.text
    assert "mystmon_node_running" in metrics
    assert "mystmon_node_api_up" in metrics


def test_deploy_scripts_wait_for_healthcheck() -> None:
    root = os.path.dirname(os.path.dirname(__file__))

    compose = open(os.path.join(root, "docker-compose.yml"), encoding="utf-8").read()
    dev_compose = open(os.path.join(root, "docker-compose.dev.yml"), encoding="utf-8").read()
    bash_install = open(os.path.join(root, "ops", "install-remote.sh"), encoding="utf-8").read()
    bash_build = open(os.path.join(root, "ops", "build-on-linux.sh"), encoding="utf-8").read()
    ps1_build = open(os.path.join(root, "ops", "build-on-linux.ps1"), encoding="utf-8").read()

    assert "healthcheck:" in compose
    assert "image: mystmon:local" in compose
    assert "container_name: mystmon-prod" in compose
    assert "ports:" in compose
    assert "healthcheck:" in dev_compose
    assert "container_name: mystmon-dev" in dev_compose
    assert "MYSTMON_SKIP_PULL" in bash_install
    assert "MYSTMON_SKIP_PULL" in bash_build
    assert "MYSTMON_SKIP_PULL" in ps1_build
    assert "docker inspect -f '{{.State.Health.Status}}' mystmon-prod" in bash_install
    assert "docker inspect -f '{{.State.Health.Status}}' mystmon-prod" in bash_build
    assert "docker inspect -f '{{.State.Health.Status}}' mystmon-prod" in ps1_build
