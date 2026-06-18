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
                    "wallet_address": "0xabc",
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
    write_collection_csv_exports(snapshot, str(tmp_path), collection_id=7)

    names = {path.name for path in written}
    assert names == {
        "collection_7_summary.csv",
        "collection_7_mystnodes_accounts.csv",
        "collection_7_mystnodes_portal_nodes.csv",
        "collection_7_mystnodes_local_nodes.csv",
    }

    summary = list(csv.reader((tmp_path / "collection_7_summary.csv").open()))
    assert summary[0] == ["collected_at", "field", "value"]
    assert summary.count(["2026-06-18T10:42:36.397201+00:00", "count.mystnodes", "2"]) == 2

    accounts = list(csv.reader((tmp_path / "collection_7_mystnodes_accounts.csv").open()))
    assert accounts[0] == [
        "collected_at",
        "account",
        "enabled",
        "authenticated",
        "base_url",
        "wallet_address",
        "node_count",
        "online_count",
        "top_os",
        "earnings_total",
        "transferred_total",
    ]
    assert accounts[1][1] == "acct-a"
    assert accounts[1][6] == "1"
    assert accounts[1][7] == "1"
    assert accounts[1][8] == "alpine"
    assert len(accounts) == 3

    portal_nodes = list(csv.reader((tmp_path / "collection_7_mystnodes_portal_nodes.csv").open()))
    assert portal_nodes[0][0:6] == ["collected_at", "account", "id", "identity", "name", "local_ip"]
    assert portal_nodes[1][1] == "acct-a"
    assert portal_nodes[1][2] == "n1"
    assert portal_nodes[1][7] == "1"
    assert len(portal_nodes) == 3

    local_nodes = list(csv.reader((tmp_path / "collection_7_mystnodes_local_nodes.csv").open()))
    assert local_nodes[0][0:6] == ["collected_at", "name", "account", "identity", "host", "running"]
    assert local_nodes[1][1] == "node-1"
    assert local_nodes[1][5] == "1"
    assert local_nodes[1][9] == "1"
    assert local_nodes[1][16] == "1"
    assert local_nodes[1][17] == "2"
    assert len(local_nodes) == 3
