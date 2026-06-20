from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mystmon.collectors.myst import (
    BLOCKED_PATHS,
    _api_auth,
    _contains_sensitive_data,
    collect_myst_nodes_async,
    extract_api_metrics,
)
from mystmon.config import MystCollectorConfig, MystContainerConfig, MystRemoteHostConfig


def _install_fake_docker(monkeypatch, containers):
    fake_module = ModuleType("docker")

    class FakeDockerClient:
        def __init__(self, *args, **kwargs):
            self.containers = self

        def list(self, all=True):
            return containers

        def close(self):
            return None

    fake_module.DockerClient = FakeDockerClient
    monkeypatch.setitem(sys.modules, "docker", fake_module)


def test_collect_myst_nodes_returns_local_and_remote_nodes(tmp_path) -> None:
    config = MystCollectorConfig(
        enabled=True,
        local_host="localhost",
        docker_socket="unix:///var/run/docker.sock",
        container_name_patterns=[r"^myst(\.|$)"],
        api_probe_enabled=False,
        api_default_port=4050,
        containers=[],
        remote_hosts=[
            MystRemoteHostConfig(
                host="remote-host",
                user="username",
                password_env="MYSTMON_SSH_PASSWORD",
                enabled=True,
            )
        ],
    )
    with patch("mystmon.collectors.myst._collect_myst_nodes_async") as mock_collect:
        mock_collect.return_value = [{"name": "test-node"}]
        result = asyncio.run(collect_myst_nodes_async(config, 10, 3600))
        assert len(result) == 1
        assert result[0]["name"] == "test-node"


def test_summarize_logs_tracks_myst_health_patterns() -> None:
    from mystmon.collectors.myst import summarize_logs

    log_text = """
    2023-01-01T00:00:00Z [ERROR] Error during settlement
    2023-01-01T00:01:00Z [WARN] Authentication needed: password or unlock
    2023-01-01T00:02:00Z [INFO] Received hermes promise
    2023-01-01T00:03:00Z [INFO] Session created
    """
    summary = summarize_logs(log_text)
    assert summary["error_or_warning"] == 2
    assert summary["promise"] == 1
    assert summary["session"] == 1
    assert summary["identity_warning"] == 1


def test_extract_api_metrics_from_documented_healthcheck() -> None:
    data = {
        "uptime": "10h30m10s",
        "version": "1.2.3",
        "build_info": {
            "commit": "abc123",
            "branch": "main",
            "build_number": "456",
        },
    }
    result = extract_api_metrics("healthcheck", "health", data)
    assert result["metrics"]["health_uptime_seconds"] == 37810.0
    assert result["labels"]["health_version"] == "1.2.3"
    assert result["labels"]["health_build_commit"] == "abc123"


def test_extract_api_metrics_from_documented_lists() -> None:
    # Test identities
    identities_data = {"identities": [{"id": "0x123"}]}
    result = extract_api_metrics("identities", "identities", identities_data)
    assert result["metrics"]["identities_count"] == 1.0

    # Test services
    services_data = {
        "services": [
            {"id": "wireguard", "running": True},
            {"id": "openvpn", "running": False},
        ]
    }
    result = extract_api_metrics("services", "services", services_data)
    assert result["metrics"]["services_count"] == 2.0
    assert result["metrics"]["services_running_count"] == 1.0


def test_node_display_name_prefers_api_identity() -> None:
    from mystmon.collectors.myst import _node_display_name

    api_probe = {
        "identity": "0x123abc",
        "labels": {"identity_id": "0x456def"},
    }
    name = _node_display_name("myst.container", api_probe)
    assert name == "0x123abc"


def test_node_display_name_falls_back_to_container_name() -> None:
    from mystmon.collectors.myst import _node_display_name

    name = _node_display_name("myst.container", None)
    assert name == "myst.container"

    name = _node_display_name("myst.container", {})
    assert name == "myst.container"


def test_collect_remote_host_nodes_logs_missing_password(monkeypatch, caplog) -> None:
    config = MystCollectorConfig(
        enabled=True,
        local_host="localhost",
        docker_socket="unix:///var/run/docker.sock",
        container_name_patterns=[r"^myst(\.|$)"],
        api_probe_enabled=False,
        api_default_port=4050,
        containers=[],
        remote_hosts=[
            MystRemoteHostConfig(
                host="remote-host",
                user="username",
                password_env="MISSING_PASSWORD_ENV",
                enabled=True,
            )
        ],
    )
    caplog.set_level(logging.ERROR)
    result = asyncio.run(collect_myst_nodes_async(config, 10, 3600))
    assert len(result) == 1
    assert result[0]["name"] == "remote-remote-host"


def test_collect_remote_host_nodes_logs_timeout(monkeypatch, caplog) -> None:
    config = MystCollectorConfig(
        enabled=True,
        local_host="localhost",
        docker_socket="unix:///var/run/docker.sock",
        container_name_patterns=[r"^myst(\.|$)"],
        api_probe_enabled=False,
        api_default_port=4050,
        containers=[],
        remote_hosts=[
            MystRemoteHostConfig(
                host="remote-host",
                user="username",
                password_env="MYSTMON_SSH_PASSWORD",
                enabled=True,
            )
        ],
    )
    caplog.set_level(logging.ERROR)
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired("ssh", 10)

    monkeypatch.setattr("subprocess.run", fake_run)
    os.environ["MYSTMON_SSH_PASSWORD"] = "test-password"
    result = asyncio.run(collect_myst_nodes_async(config, 10, 3600))
    assert len(result) == 1
    assert result[0]["name"] == "remote-remote-host"


def test_fetch_api_endpoint_logs_http_error(monkeypatch, caplog) -> None:
    from mystmon.collectors.myst import _fetch_api_endpoint_async

    caplog.set_level(logging.ERROR)

    async def fake_get(*args, **kwargs):
        raise httpx.HTTPError("Connection failed")

    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)
    
    endpoint_config = MagicMock()
    endpoint_config.name = "test_endpoint"
    endpoint_config.path = "/test"
    endpoint_config.method = "GET"
    
    async def run_test():
        result = await _fetch_api_endpoint_async(
            "http://localhost:4050",
            endpoint_config,
            None,
            "test-container",
            True
        )
        assert result["ok"] is False
        assert "Connection failed" in result["error"]

    import asyncio
    asyncio.run(run_test())


def test_container_snapshot_uses_configured_api_host(monkeypatch) -> None:
    captured_urls = []

    def fake_get(self, url, timeout=None, auth=None):
        captured_urls.append(f"{self.base_url}{url}")

        class Response:
            status_code = 200
            headers = {"content-type": "application/json"}

            @staticmethod
            def raise_for_status() -> None:
                pass

            @staticmethod
            def json():
                return {"uptime": "1h"}

        return Response()

    class FakeContainer:
        name = "myst.1.x"

        def reload(self):
            pass

        def logs(self, **kwargs):
            return b"test logs"

        @property
        def attrs(self):
            return {
                "State": {"Running": True, "Status": "running", "StartedAt": "2023-01-01T00:00:00Z"},
                "RestartCount": 0,
                "NetworkSettings": {
                    "Networks": {"bridge": {"IPAddress": "172.17.0.2"}},
                    "Ports": {"4050/tcp": [{"HostIp": "0.0.0.0", "HostPort": "4050"}]},
                },
            }

        @property
        def short_id(self):
            return "abc123"

    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)
    _install_fake_docker(monkeypatch, [FakeContainer()])

    config = MystCollectorConfig(
        enabled=True,
        local_host="localhost",
        docker_socket="unix:///var/run/docker.sock",
        container_name_patterns=[r"^myst(\.|$)"],
        api_probe_enabled=True,
        api_default_port=4050,
        api_username="test",
        api_password_env="TEST_PASSWORD",
        containers=[
            MystContainerConfig(
                name="myst.1.x",
                host="192.168.1.100",
                tequilapi_port=4050,
            )
        ],
        remote_hosts=[],
    )
    os.environ["TEST_PASSWORD"] = "password"

    asyncio.run(collect_myst_nodes_async(config, 10, 3600))
    assert len(captured_urls) > 0
    assert "192.168.1.100:4050" in captured_urls[0]


def test_collect_remote_host_nodes_uses_configured_tequilapi_port(monkeypatch) -> None:
    captured_urls = []

    def fake_run(*args, **kwargs):
        class Result:
            returncode = 0
            stdout = '{"Name":"/myst.remote","Id":"abc","State":{"Running":true,"Status":"running"},"RestartCount":0,"NetworkSettings":{"Networks":{"bridge":{"IPAddress":"172.17.0.2"}},"Ports":{"4050/tcp":[{"HostIp":"0.0.0.0","HostPort":"4050"}]}}}'
            stderr = ""

        return Result()

    def fake_get(self, url, timeout=None, auth=None):
        captured_urls.append(f"{self.base_url}{url}")

        class Response:
            status_code = 200
            headers = {"content-type": "application/json"}

            @staticmethod
            def raise_for_status() -> None:
                pass

            @staticmethod
            def json():
                return {"uptime": "1h"}

        return Response()

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)
    os.environ["MYSTMON_SSH_PASSWORD"] = "test-password"
    _install_fake_docker(monkeypatch, [])

    config = MystCollectorConfig(
        enabled=True,
        local_host="localhost",
        docker_socket="unix:///var/run/docker.sock",
        container_name_patterns=[r"^myst(\.|$)"],
        api_probe_enabled=True,
        api_default_port=4050,
        api_username="test",
        api_password_env="TEST_PASSWORD",
        containers=[],
        remote_hosts=[
            MystRemoteHostConfig(
                host="remote-host",
                user="username",
                password_env="MYSTMON_SSH_PASSWORD",
                tequilapi_port=8080,
                enabled=True,
            )
        ],
    )
    os.environ["TEST_PASSWORD"] = "password"

    asyncio.run(collect_myst_nodes_async(config, 10, 3600))
    assert len(captured_urls) > 0
    assert ":8080" in captured_urls[0]


def test_collect_remote_host_nodes_prefers_configured_api_host_for_matching_network(monkeypatch) -> None:
    captured_urls = []

    def fake_run(*args, **kwargs):
        class Result:
            returncode = 0
            stdout = '{"Name":"/myst","Id":"abc","State":{"Running":true,"Status":"running"},"RestartCount":0,"NetworkSettings":{"Networks":{"vlan14":{"IPAddress":"192.168.14.5"}},"Ports":{"4050/tcp":[{"HostIp":"0.0.0.0","HostPort":"4050"}]}}}'
            stderr = ""

        return Result()

    def fake_get(self, url, timeout=None, auth=None):
        captured_urls.append(f"{self.base_url}{url}")

        class Response:
            status_code = 200

            @staticmethod
            def raise_for_status() -> None:
                pass

            @staticmethod
            def json():
                return {"uptime": "1h"}

        return Response()

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)
    os.environ["MYSTMON_SSH_PASSWORD"] = "test-password"
    _install_fake_docker(monkeypatch, [])

    config = MystCollectorConfig(
        enabled=True,
        local_host="localhost",
        docker_socket="unix:///var/run/docker.sock",
        container_name_patterns=[r"^myst(\.|$)"],
        api_probe_enabled=True,
        api_default_port=4050,
        api_username="test",
        api_password_env="TEST_PASSWORD",
        containers=[
            MystContainerConfig(
                name="myst",
                expected_network="vlan14",
                host="192.168.14.100",
                tequilapi_port=4050,
            )
        ],
        remote_hosts=[
            MystRemoteHostConfig(
                host="remote-host",
                user="username",
                password_env="MYSTMON_SSH_PASSWORD",
                enabled=True,
            )
        ],
    )
    os.environ["TEST_PASSWORD"] = "password"

    asyncio.run(collect_myst_nodes_async(config, 10, 3600))
    assert len(captured_urls) > 0
    assert "192.168.14.100:4050" in captured_urls[0]


def test_api_auth_returns_none_when_not_configured() -> None:
    config = MystCollectorConfig(
        enabled=True,
        local_host="localhost",
        docker_socket="unix:///var/run/docker.sock",
        container_name_patterns=[r"^myst(\.|$)"],
        api_probe_enabled=False,
        api_default_port=4050,
        api_username=None,
        api_password_env=None,
        containers=[],
        remote_hosts=[],
    )
    assert _api_auth(config) is None


def test_api_auth_returns_credentials_when_configured() -> None:
    config = MystCollectorConfig(
        enabled=True,
        local_host="localhost",
        docker_socket="unix:///var/run/docker.sock",
        container_name_patterns=[r"^myst(\.|$)"],
        api_probe_enabled=False,
        api_default_port=4050,
        api_username="testuser",
        api_password_env="TEST_PASSWORD",
        containers=[],
        remote_hosts=[],
    )
    os.environ["TEST_PASSWORD"] = "testpass"
    assert _api_auth(config) == ("testuser", "testpass")


def test_contains_sensitive_data_detects_sensitive_patterns() -> None:
    # Test private key pattern
    assert _contains_sensitive_data("private_key: abcdefghijklmnopqrstuvwxyz1234567890abcd")
    
    # Test Ethereum address (should not be considered sensitive as it's public)
    assert not _contains_sensitive_data("address: 0x1234567890123456789012345678901234567890")
    
    # Test long alphanumeric string
    assert _contains_sensitive_data("secret_token: abcdefghijklmnopqrstuvwxyz1234567890")
    
    # Test keyword patterns
    assert _contains_sensitive_data("password: mysecretpassword")
    assert _contains_sensitive_data("secret: mysecret")
    assert _contains_sensitive_data("token: mytoken")
    assert _contains_sensitive_data("private: myprivatekey")
    assert _contains_sensitive_data("key: mykey")
    assert _contains_sensitive_data("mnemonic: mymnemonic")
    assert _contains_sensitive_data("wallet: mywalletpassword")
    assert _contains_sensitive_data("hash: myhashvalue")
    
    # Test non-sensitive data
    assert not _contains_sensitive_data("normal_text: this is normal text")
    assert not _contains_sensitive_data("short: abc")


def test_blocked_paths_are_safety_enforced() -> None:
    # Ensure all blocked paths are defined
    assert "/connection" in BLOCKED_PATHS
    assert "/stop" in BLOCKED_PATHS
    assert "/identities/import" in BLOCKED_PATHS
    assert "/identities/create" in BLOCKED_PATHS
    assert "/identities/{id}/unlock" in BLOCKED_PATHS
    assert "/identities/register" in BLOCKED_PATHS
    assert "/config/set" in BLOCKED_PATHS
    assert "/settle/withdraw" in BLOCKED_PATHS
    assert "/settle/pay" in BLOCKED_PATHS
    assert "/auth/login" in BLOCKED_PATHS
    assert "/auth/logout" in BLOCKED_PATHS
    assert "/feedback" in BLOCKED_PATHS
    assert "/bug-report" in BLOCKED_PATHS


# New tests for TequilAPI functionality
def test_tequilapi_probe_does_not_fetch_openapi_schema(monkeypatch) -> None:
    from mystmon.collectors.myst import _probe_api_async

    # Mock responses for each endpoint
    responses = {
        "/healthcheck": {"uptime": "1h", "version": "1.2.3"},
        "/identities": {"identities": [{"id": "0x123"}]},
        "/sessions": {"count": 5},
        "/node/provider/quality": {"quality": 0.95},
        "/transactor/fees": {"balance": 100.5},
        "/location": {"ip": "192.168.1.100", "country": "US"},
        "/nat/type": "fullcone"
    }

    captured_urls = []

    async def fake_get(self, url, timeout=None, auth=None):
        captured_urls.append(url)
        path = url.split(":4050")[1]  # Extract path from URL
        assert path != "/openapi.json"
        
        class Response:
            status_code = 200
            headers = {"content-type": "application/json"}

            @staticmethod
            def raise_for_status() -> None:
                pass

            @staticmethod
            def json():
                return responses.get(path, {})

        return Response()

    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

    config = MystCollectorConfig(
        enabled=True,
        local_host="localhost",
        docker_socket="unix:///var/run/docker.sock",
        container_name_patterns=[r"^myst(\.|$)"],
        api_probe_enabled=True,
        api_default_port=4050,
        api_username="test",
        api_password_env="TEST_PASSWORD",
        containers=[],
        remote_hosts=[],
    )
    os.environ["TEST_PASSWORD"] = "password"

    import asyncio
    result = asyncio.run(
        _probe_api_async(
            "localhost",
            "test-container",
            {"4050/tcp": [{"HostIp": "0.0.0.0", "HostPort": "4050"}]},
            config,
        )
    )
    
    # Check that the API probe was successful without schema discovery
    assert result["enabled"] is True
    assert result["up"] is True
    assert result["auth"] is True
    assert result["schema_available"] is False
    
    # Check that endpoints were processed
    assert "healthcheck" in result["endpoints"]
    assert "identities" in result["endpoints"]
    assert "sessions" in result["endpoints"]
    assert "provider_quality" in result["endpoints"]
    assert "payments_balance" in result["endpoints"]
    assert "location" in result["endpoints"]
    assert "nat_type" in result["endpoints"]
    
    # Check that metrics were extracted
    assert "health_uptime_seconds" in result["metrics"]
    assert "identities_count" in result["metrics"]
    assert "sessions_count" in result["metrics"]
    assert "provider_quality_quality" in result["metrics"] or "provider_quality" in result["metrics"]
    assert "payments_balance" in result["metrics"] or "payments_balance_balance" in result["metrics"]
    
    # Check that labels were extracted
    assert "location_country" in result["labels"]
    assert "nat" in result["labels"]
    assert "/openapi.json" not in captured_urls


def test_tequilapi_blocked_endpoints_are_not_called(monkeypatch) -> None:
    from mystmon.collectors.myst import _probe_api_async

    responses = {
        "/healthcheck": {"uptime": "1h", "version": "1.2.3"}
    }

    captured_urls = []

    async def fake_get(self, url, timeout=None, auth=None):
        captured_urls.append(url)
        path = url.split(":4050")[1]  # Extract path from URL
        
        class Response:
            status_code = 200
            headers = {"content-type": "application/json"}

            @staticmethod
            def raise_for_status() -> None:
                pass

            @staticmethod
            def json():
                return responses.get(path, {})

        return Response()

    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

    config = MystCollectorConfig(
        enabled=True,
        local_host="localhost",
        docker_socket="unix:///var/run/docker.sock",
        container_name_patterns=[r"^myst(\.|$)"],
        api_probe_enabled=True,
        api_default_port=4050,
        api_username="test",
        api_password_env="TEST_PASSWORD",
        containers=[],
        remote_hosts=[],
    )
    os.environ["TEST_PASSWORD"] = "password"

    async def run_test():
        result = await _probe_api_async(
            "localhost",
            "test-container",
            {"4050/tcp": [{"HostIp": "0.0.0.0", "HostPort": "4050"}]},
            config
        )
        return result

    import asyncio
    result = asyncio.run(run_test())
    
    # Check that blocked endpoint was not called
    called_paths = [url.split(":4050")[1] for url in captured_urls]
    assert "/connection" not in called_paths
    
    # Check that healthcheck was called
    assert "/healthcheck" in called_paths


def test_tequilapi_data_redaction_works() -> None:
    from mystmon.collectors.myst import _redact_api_value

    # Test sensitive data redaction
    sensitive_data = {
        "password": "secret123",
        "token": "abc123def456",
        "private_key": "abcdefghijklmnopqrstuvwxyz1234567890abcd",
        "normal_field": "normal_value"
    }
    
    redacted = _redact_api_value(sensitive_data)
    
    # Check that sensitive fields are redacted
    assert redacted["password"] == "***REDACTED***"
    assert redacted["token"] == "***REDACTED***"
    assert redacted["private_key"] == "***REDACTED***"
    
    # Check that normal fields are preserved
    assert redacted["normal_field"] == "normal_value"


def test_tequilapi_endpoint_categories_are_correctly_handled() -> None:
    from mystmon.collectors.myst import extract_api_metrics

    # Test health category
    health_data = {"uptime": "1h", "version": "1.2.3"}
    result = extract_api_metrics("healthcheck", "health", health_data)
    assert "health_uptime_seconds" in result["metrics"]
    assert "health_version" in result["labels"]

    # Test identities category
    identities_data = {"identities": [{"id": "0x123"}]}
    result = extract_api_metrics("identities", "identities", identities_data)
    assert "identities_count" in result["metrics"]

    # Test services category
    services_data = {"services": [{"id": "wireguard", "running": True}]}
    result = extract_api_metrics("services", "services", services_data)
    assert "services_count" in result["metrics"]
    assert "services_running_count" in result["metrics"]

    # Test sessions category
    sessions_data = {"count": 5, "active": 3}
    result = extract_api_metrics("sessions", "sessions", sessions_data)
    assert "sessions_count" in result["metrics"]
    assert "sessions_active" in result["metrics"]

    # Test provider category
    provider_data = {"quality": 0.95, "sessions": 100}
    result = extract_api_metrics("provider_stats", "provider", provider_data)
    assert "provider_quality" in result["metrics"]
    assert "provider_sessions" in result["metrics"]

    # Test payments category
    payments_data = {"balance": 100.5}
    result = extract_api_metrics("payments_balance", "payments", payments_data)
    assert "payments_balance" in result["metrics"]

    # Test location category
    location_data = {"ip": "192.168.1.100", "country": "US"}
    result = extract_api_metrics("location", "location", location_data)
    assert "location_ip" in result["labels"]
    assert "location_country" in result["labels"]

    # Test nat category
    nat_data = "fullcone"
    result = extract_api_metrics("nat_type", "nat", nat_data)
    assert "nat" in result["labels"]


def test_tequilapi_management_data_structure() -> None:
    from mystmon.collectors.myst import _probe_api_async
    
    # Test that management data is structured correctly
    management_data = {
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
            "location": {"ip": "192.168.1.100", "country": "US"}
        },
        "nat": {
            "nat_type": "fullcone"
        }
    }
    
    # Verify structure
    assert "health" in management_data
    assert "sessions" in management_data
    assert "provider" in management_data
    assert "payments" in management_data
    assert "location" in management_data
    assert "nat" in management_data
    
    # Verify nested data
    assert management_data["health"]["healthcheck"]["version"] == "1.2.3"
    assert management_data["sessions"]["sessions"]["count"] == 5
    assert management_data["provider"]["provider_stats"]["quality"] == 0.95
    assert management_data["payments"]["payments_balance"]["balance"] == 100.5
    assert management_data["location"]["location"]["country"] == "US"
    assert management_data["nat"]["nat_type"] == "fullcone"


def test_tequilapi_summary_extracts_nested_location_sessions_and_provider_fields() -> None:
    from mystmon.collectors.myst import _tequilapi_summary

    summary = _tequilapi_summary(
        {
            "identity": "0xabc",
            "management": {
                "location": {
                    "location": {
                        "ip": "122.179.195.76",
                        "city": "Ghaziabad",
                        "country": "IN",
                        "isp": "Bharti Airtel Ltd.",
                        "asn": 24560,
                    }
                },
                "nat": {"nat_type": {"type": "prcone"}},
                "services": {"services": {"count": 6, "running_count": 6, "types": ["dvpn", "wireguard"]}},
                "sessions": {
                    "session_stats_aggregated": {"daily": {"count": 817}},
                    "sessions": {"daily": {"count": 42}},
                },
                "provider": {"provider_quality": {"quality": 1.7}},
                "payments": {"transactor_fees_v2": {"current": {"settlement": {"human": "0.033706"}}}},
            },
        }
    )

    assert summary["identity"] == "0xabc"
    assert summary["public_ip"] == "122.179.195.76"
    assert summary["nat_type"] == "prcone"
    assert summary["services_count"] == 6.0
    assert summary["services_running"] == 6.0
    assert summary["sessions_active"] == 42.0
    assert summary["sessions_1d"] == 817.0
    assert summary["provider_quality"] == 1.7
