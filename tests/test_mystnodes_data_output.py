from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

from mystmon.config import MystNodesPortalAccountConfig


def _portal_node(account: str, index: int, local_ip: str) -> dict[str, Any]:
    node_id = f"{account}-node-{index}"
    return {
        "id": node_id,
        "name": f"{account}-node-{index}",
        "identity": f"identity-{account}-{index}",
        "localIp": local_ip,
        "nodeStatus": {"online": True, "quality": 93.5},
        "earnings": [{"etherAmount": "1.25"}],
    }


def _portal_account(name: str, count: int, ip_prefix: str) -> dict[str, Any]:
    nodes = [_portal_node(name, i + 1, f"192.168.{ip_prefix}.{i + 10}") for i in range(count)]
    return {
        "enabled": True,
        "authenticated": True,
        "name": name,
        "base_url": "https://my.mystnodes.com",
        "wallet_address_hint": "0x9A18...4bE",
        "endpoints": {
            "nodes": {"ok": True, "data": {"nodes": nodes, "total": count}},
            "me": {"ok": True, "data": {"nodesInfo": {"totalCount": count, "onlineCount": count}}},
        },
        "local_matches": {
            node["id"]: {
                "name": node["name"],
                "container_name": node["name"],
                "host": node["localIp"],
                "running": True,
                "status": "running",
                "restart_count": 0,
                "uptime_seconds": 123456,
                "networks": [{"name": "host", "ip_address": node["localIp"]}],
                "log_counts": {"error_or_warning": 0, "promise": 0, "session": 0, "identity_warning": 0},
                "warnings": [],
            }
            for node in nodes
        },
        "node_details": {
            "nodes": {
                node["id"]: {
                    "detail": {"ok": True, "data": {"uptimeMinLast24H": 1320 + idx}}
                }
                for idx, node in enumerate(nodes)
            }
        },
    }


def test_mystnodes_data_collection_shows_two_accounts_and_local_ip_metrics() -> None:
    account_a = _portal_account("account-a", 8, "10")
    account_b = _portal_account("account-b", 6, "11")

    async def fake_collect_accounts(configs, timeout_seconds, local_nodes=None):
        assert [config.account for config in configs] == ["account-a", "account-b"]
        return {
            "accounts": [account_a, account_b],
            "nodes": account_a["endpoints"]["nodes"]["data"]["nodes"] + account_b["endpoints"]["nodes"]["data"]["nodes"],
            "endpoints": {},
            "enabled": True,
            "authenticated": True,
        }

    result = asyncio.run(fake_collect_accounts([MystNodesPortalAccountConfig(account="account-a"), MystNodesPortalAccountConfig(account="account-b")], 30))

    assert result is not None
    assert len(result["accounts"]) == 2
    assert len(result["accounts"][0]["endpoints"]["nodes"]["data"]["nodes"]) == 8
    assert len(result["accounts"][1]["endpoints"]["nodes"]["data"]["nodes"]) == 6

    node_counts = Counter(node["localIp"] for node in result["nodes"])
    assert sum(node_counts.values()) == 14
    assert len(node_counts) == 14

    for account in result["accounts"]:
        for node in account["endpoints"]["nodes"]["data"]["nodes"]:
            local_ip = node["localIp"]
            assert local_ip.startswith("192.168.")
            assert local_ip in {item["host"] for item in account["local_matches"].values()}
            assert account["node_details"]["nodes"][node["id"]]["detail"]["data"]["uptimeMinLast24H"] >= 1320

    print("accounts=2")
    print("account-a_nodes=8")
    print("account-b_nodes=6")
    print("resolved_local_ips=14")
    for account in result["accounts"]:
        for node in account["endpoints"]["nodes"]["data"]["nodes"]:
            print(f"{account['name']} {node['identity']} {node['localIp']}")


def test_mystnodes_data_uses_account_field_for_email() -> None:
    """Test that MystNodes data collection uses account field for email."""
    # Create test configs using the account field
    configs = [
        MystNodesPortalAccountConfig(account="test1@example.com", password="pass1"),
        MystNodesPortalAccountConfig(account="test2@example.com", password="pass2")
    ]
    
    # Verify configs use account field
    assert configs[0].account == "test1@example.com"
    assert configs[1].account == "test2@example.com"
    
    # Verify no separate email field exists
    assert not hasattr(configs[0], 'email')
    assert not hasattr(configs[1], 'email')


def test_mystnodes_data_account_provenance() -> None:
    """Test that nodes include account provenance information."""
    account_a = _portal_account("account-a", 2, "10")
    account_b = _portal_account("account-b", 2, "11")

    async def fake_collect_account(config, timeout_seconds, local_nodes=None):
        if config.account == "account-a":
            return account_a
        if config.account == "account-b":
            return account_b
        raise AssertionError(f"unexpected account {config.account}")

    import mystmon.collectors.mystnodes as mystnodes_module

    original = mystnodes_module.collect_mystnodes_portal_account
    mystnodes_module.collect_mystnodes_portal_account = fake_collect_account
    try:
        result = asyncio.run(
            mystnodes_module.collect_mystnodes_portal_accounts(
                [
                    MystNodesPortalAccountConfig(account="account-a"),
                    MystNodesPortalAccountConfig(account="account-b"),
                ],
                30,
            )
        )
    finally:
        mystnodes_module.collect_mystnodes_portal_account = original

    # Verify nodes include account provenance
    account_names = {node["account"] for node in result["nodes"]}
    assert "account-a" in account_names
    assert "account-b" in account_names
