from __future__ import annotations

import csv
from pathlib import Path

from mystmon.export_csv import write_collection_csv_exports


def _sample_snapshot() -> dict:
    return {
        "generated_at": "2026-06-18T10:42:36.397201+00:00",
        "collection_counts": {"myst": 2, "mystnodes": 2, "prometheus": 0, "snmp": 0},
        "mystnodes": {
            "accounts": [
                {
                    "name": "acct-a",
                    "enabled": True,
                    "authenticated": True,
                    "base_url": "https://my.mystnodes.com",
                    "wallet_address_hint": "0xabc...cdef",
                    "endpoints": {
                        "me": {"ok": True, "data": {"nodesInfo": {"totalCount": 2, "onlineCount": 1, "topOS": "alpine"}}},
                        "nodes": {"ok": True, "data": {"nodes": [
                            {
                                "id": "n1",
                                "identity": "id-1",
                                "name": "node-1",
                                "localIp": "192.168.1.10",
                                "externalIp": "1.2.3.4",
                                "version": "1.0.0",
                                "os": "Alpine",
                                "monitoringStatus": "success",
                                "createdAt": "2026-06-18T10:00:00Z",
                                "updatedAt": "2026-06-18T10:05:00Z",
                                "earnings": [{"etherAmount": "1.25"}],
                                "nodeStatus": {"online": True, "quality": 2.5, "serviceTypes": ["dvpn", "scraping"]},
                            }
                        ]}},
                        "wallet_balance": {"ok": True, "data": {"current": {"settlement": {"human": "0.033706"}}}},
                        "total_earnings": {"ok": True, "data": {"earningsTotal": 9.5}},
                        "total_transferred": {"ok": True, "data": {"transferredTotal": 17}},
                    },
                }
            ]
        },
        "nodes": [
            {
                "name": "node-1",
                "account": "acct-a",
                "identity": "id-1",
                "host": "192.168.1.10",
                "running": True,
                "status": "running",
                "restart_count": 0,
                "uptime_seconds": 123,
                "api": {
                    "up": True,
                    "status_code": 200,
                    "identity": "id-1",
                    "endpoints": {
                        "sessions": {"data": {"total_items": 3}},
                        "sessions_connectivity_status": {"data": {"entries": [{"code": 1000}, {"code": 2003}]}},
                        "session_stats_aggregated": {"data": {"stats": {
                            "count": 11,
                            "count_consumers": 7,
                            "sum_bytes_received": 1000,
                            "sum_bytes_sent": 2000,
                            "sum_duration": 3000,
                            "sum_tokens": 4000,
                        }}},
                        "provider_activity_stats": {"data": {"active_percent": 90.5, "online_percent": 100}},
                        "provider_service_earnings": {"data": {
                            "public_tokens": {"human": "1.1"},
                            "data_transfer_tokens": {"human": "2.2"},
                            "scraping_tokens": {"human": "3.3"},
                            "dvpn_tokens": {"human": "4.4"},
                            "monitoring_tokens": {"human": "5.5"},
                        }},
                        "transactor_fees_v2": {"data": {
                            "hermes_percent": "0.2000",
                            "current": {
                                "registration": {"human": "0.077"},
                                "settlement": {"human": "0.035"},
                                "decrease_stake": {"human": "0.026"},
                            }
                        }},
                        "config": {"data": {"data": {
                            "active-services": "dvpn,data_transfer",
                            "tequilapi": {"address": "0.0.0.0", "port": 4050},
                            "discovery": {"type": ["api"]},
                        }}},
                        "location": {"data": {"ip": "9.9.9.9", "city": "Delhi", "country": "IN"}},
                        "nat_type": {"data": {"type": "prcone"}},
                    },
                    "metrics": {
                        "provider_quality": 2.5,
                        "provider_sessions_1d_count": 1,
                        "provider_sessions_7d_count": 2,
                    },
                },
            }
        ],
    }


def test_write_collection_csv_exports_creates_sectioned_files(tmp_path: Path) -> None:
    snapshot = _sample_snapshot()

    written = write_collection_csv_exports(snapshot, str(tmp_path), collection_id=7)
    second_written = write_collection_csv_exports(snapshot, str(tmp_path), collection_id=8)

    names = {path.name for path in written}
    assert names == {
        "summary.csv",
        "mystnodes_accounts.csv",
        "mystnodes_portal_nodes.csv",
        "mystnodes_local_runtime_nodes.csv",
        "mystnodes_local_hosts.csv",
    }
    assert {path.name for path in second_written} == names

    summary = list(csv.reader((tmp_path / "summary.csv").open()))
    assert summary[0] == ["collected_at", "field", "value"]
    assert summary.count(["2026-06-18T10:42:36.397201+00:00", "count.mystnodes", "2"]) == 2

    accounts = list(csv.reader((tmp_path / "mystnodes_accounts.csv").open()))
    assert accounts[0] == [
        "collected_at",
        "account",
        "enabled",
        "authenticated",
        "base_url",
        "wallet_address_hint",
        "wallet_balance_ok",
        "wallet_balance_state",
        "node_count",
        "online_count",
        "top_os",
        "earnings_total",
        "transferred_total",
    ]
    assert accounts[1][1] == "acct-a"
    assert accounts[1][5] == "0xabc...cdef"
    assert accounts[1][6] == "1"
    assert accounts[1][7] == "0.033706"
    assert accounts[1][8] == "1"
    assert accounts[1][9] == "1"
    assert accounts[1][10] == "alpine"
    assert len(accounts) == 3

    portal_nodes = list(csv.reader((tmp_path / "mystnodes_portal_nodes.csv").open()))
    assert portal_nodes[0][0:6] == ["collected_at", "account", "id", "identity", "name", "local_ip"]
    assert portal_nodes[1][1] == "acct-a"
    assert portal_nodes[1][2] == "n1"
    assert portal_nodes[1][7] == "1"
    assert len(portal_nodes) == 3

    local_runtime_nodes = list(csv.reader((tmp_path / "mystnodes_local_runtime_nodes.csv").open()))
    assert local_runtime_nodes[0][0:6] == ["collected_at", "host", "container_name", "portal_account", "portal_identity", "portal_node_name"]
    idx = {name: i for i, name in enumerate(local_runtime_nodes[0])}
    row = local_runtime_nodes[1]
    assert row[idx["host"]] == "192.168.1.10"
    assert row[idx["portal_account"]] == "acct-a"
    assert row[idx["running"]] == "1"
    assert row[idx["api_up"]] == "1"
    assert row[idx["api_provider_quality"]] == "2.5"
    assert row[idx["api_sessions_7d"]] == "2"
    assert row[idx["api_sessions_total_items"]] == "3"
    assert row[idx["api_sessions_agg_count"]] == "11"
    assert row[idx["api_payment_hermes_percent"]] == "0.2000"
    assert row[idx["api_payment_registration_human"]] == "0.077"
    assert row[idx["api_provider_active_percent"]] == "90.5"
    assert row[idx["api_provider_public_earnings_human"]] == "1.1"
    assert row[idx["api_config_active_services"]] == "dvpn,data_transfer"
    assert row[idx["api_config_tequilapi_address"]] == "0.0.0.0"
    assert row[idx["api_config_tequilapi_port"]] == "4050"
    assert row[idx["api_config_discovery_type"]] == '["api"]'
    assert len(local_runtime_nodes) == 3

    local_hosts = list(csv.reader((tmp_path / "mystnodes_local_hosts.csv").open()))
    assert local_hosts[0] == [
        "collected_at",
        "host",
        "matched_runtime_count",
        "matched_portal_node_count",
        "running_count",
        "accounts",
        "identities",
        "portal_node_names",
        "container_names",
    ]
    assert len(local_hosts) == 3
    assert local_hosts[1][1] == "192.168.1.10"


def test_write_collection_csv_exports_preserves_local_timezone_timestamp(tmp_path: Path) -> None:
    snapshot = _sample_snapshot()
    snapshot["generated_at"] = "2026-06-18T16:12:36.397201+05:30"

    write_collection_csv_exports(snapshot, str(tmp_path), collection_id=7)

    summary = list(csv.reader((tmp_path / "summary.csv").open()))
    assert summary[1][0] == "2026-06-18T16:12:36.397201+05:30"


def test_write_collection_csv_exports_prefers_portal_local_matches_for_local_nodes(tmp_path: Path) -> None:
    snapshot = {
        "generated_at": "2026-06-19T18:48:35.758035+00:00",
        "collection_counts": {"myst": 4, "mystnodes": 2},
        "nodes": [
            {
                "name": "remote-192.168.1.173",
                "host": "192.168.1.173",
                "running": True,
                "status": "running",
                "restart_count": 0,
                "uptime_seconds": None,
            }
        ],
        "mystnodes": {
            "nodes": [
                {
                    "id": "portal-1",
                    "account": "acct-a",
                    "identity": "id-1",
                    "name": "node-a",
                    "localIp": "192.168.1.10",
                    "nodeStatus": {"quality": 2.5},
                }
            ],
            "local_matches": {
                "portal-1": {
                    "name": "myst.1.x",
                    "container_name": "myst.1.x",
                    "host": "192.168.1.10",
                    "running": True,
                    "status": "running",
                    "restart_count": 0,
                    "uptime_seconds": 123,
                }
            },
        },
    }

    write_collection_csv_exports(snapshot, str(tmp_path), collection_id=7)

    local_runtime_nodes = list(csv.reader((tmp_path / "mystnodes_local_runtime_nodes.csv").open()))
    assert len(local_runtime_nodes) == 2
    assert local_runtime_nodes[1][1] == "192.168.1.10"
    assert local_runtime_nodes[1][2] == "myst.1.x"
    assert local_runtime_nodes[1][3] == "acct-a"
    assert local_runtime_nodes[1][4] == "id-1"
    assert local_runtime_nodes[1][17] == "2.5"

    local_hosts = list(csv.reader((tmp_path / "mystnodes_local_hosts.csv").open()))
    assert len(local_hosts) == 2
    assert local_hosts[1][1] == "192.168.1.10"
    assert local_hosts[1][2] == "1"
    assert local_hosts[1][3] == "1"
