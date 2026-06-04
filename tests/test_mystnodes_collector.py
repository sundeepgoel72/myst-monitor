import asyncio

from mystmon.collectors.mystnodes import _fetch_endpoint, _match_local_nodes
from mystmon.config import MystNodesPortalConfig, MystNodesPortalEndpointConfig


def test_match_local_nodes_uses_portal_local_ip() -> None:
    matches = _match_local_nodes(
        [
            {
                "id": "portal-1",
                "name": "node-one",
                "localIp": "192.0.2.71",
            }
        ],
        [
            {
                "name": "myst.12.x",
                "container_name": "myst.12.x",
                "host": "example-host",
                "running": True,
                "status": "running",
                "restart_count": 0,
                "uptime_seconds": 120,
                "networks": [{"name": "ipvlan12", "ip_address": "192.0.2.71"}],
                "log_counts": {"error_or_warning": 2},
                "warnings": ["failed to sign metrics"],
            }
        ],
    )

    assert matches["portal-1"]["container_name"] == "myst.12.x"
    assert matches["portal-1"]["running"] is True
    assert matches["portal-1"]["log_counts"]["error_or_warning"] == 2


def test_match_local_nodes_handles_host_network_container() -> None:
    matches = _match_local_nodes(
        [{"id": "portal-1", "name": "node-one", "localIp": "example-host"}],
        [
            {
                "name": "myst.1.x",
                "container_name": "myst.1.x",
                "host": "example-host",
                "running": True,
                "status": "running",
                "restart_count": 0,
                "uptime_seconds": 120,
                "networks": [{"name": "host", "ip_address": ""}],
                "log_counts": {"error_or_warning": 0},
                "warnings": [],
            }
        ],
    )

    assert matches["portal-1"]["container_name"] == "myst.1.x"


def test_wallet_balance_endpoint_uses_configured_wallet_address(monkeypatch) -> None:
    captured = {}

    async def fake_request_json(client, config, method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["params"] = kwargs.get("params")
        return {"ok": True, "status_code": 200, "data": {"ok": True}}

    monkeypatch.setattr("mystmon.collectors.mystnodes._request_json", fake_request_json)

    endpoint = MystNodesPortalEndpointConfig(name="wallet_balance", path="/api/v2/node/balance")
    config = MystNodesPortalConfig(wallet_address="0x9A183F79b7b803DF658DB0aC6159f0016e9db4bE")

    result = asyncio.run(_fetch_endpoint(object(), config, endpoint, {}))

    assert result is not None
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v2/node/balance"
    assert captured["params"]["walletAddress"] == "0x9A183F79b7b803DF658DB0aC6159f0016e9db4bE"
    assert captured["params"]["address"] == "0x9A183F79b7b803DF658DB0aC6159f0016e9db4bE"
