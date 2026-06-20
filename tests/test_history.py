from __future__ import annotations

from datetime import UTC, datetime

from mystmon.bootstrap import bootstrap_storage
from mystmon.history import HistoryStore


def test_history_appends_snapshots_and_calculates_delta(tmp_path) -> None:
    bootstrap_storage(str(tmp_path / "mystmon.db"), str(tmp_path / "latest.json"), str(tmp_path / "snmp_extend.txt"))
    store = HistoryStore(str(tmp_path / "mystmon.db"), timezone_name="Asia/Kolkata")
    first = _snapshot(datetime(2026, 5, 24, 2, 0, tzinfo=UTC), earnings=10.0, quality=2.0, warnings=1)
    second = _snapshot(datetime(2026, 5, 25, 3, 0, tzinfo=UTC), earnings=12.5, quality=2.5, warnings=4)

    store.append_snapshot(first)
    store.append_snapshot(second)

    latest = store.latest_collection()
    delta = store.delta(hours=24)

    assert latest is not None
    assert latest["counts"]["myst"] == 1
    assert delta["ok"] is True
    assert delta["fleet"]["delta"]["earnings_total"] == 2.5
    assert delta["fleet"]["delta"]["quality_avg"] == 0.5
    assert delta["fleet"]["current"]["running"] == 1.0
    assert delta["fleet"]["delta"]["running"] == 0.0
    assert delta["nodes"][0]["current"]["running"] == 1.0
    assert delta["fleet"]["delta"]["log_error_or_warning"] == 3.0
    assert delta["nodes"][0]["delta"]["earnings_total"] == 2.5


def test_history_missing_prior_values_are_unknown(tmp_path) -> None:
    bootstrap_storage(str(tmp_path / "mystmon.db"), str(tmp_path / "latest.json"), str(tmp_path / "snmp_extend.txt"))
    store = HistoryStore(str(tmp_path / "mystmon.db"), timezone_name="Asia/Kolkata")
    store.append_snapshot(_snapshot(datetime(2026, 5, 25, 3, 0, tzinfo=UTC), earnings=12.5, quality=2.5))

    delta = store.delta(hours=24)

    assert delta["prior"] is None
    assert delta["fleet"]["delta"]["earnings_total"] == "unknown"
    assert delta["nodes"][0]["delta"]["quality"] == "unknown"


def test_report_records_prevent_duplicates(tmp_path) -> None:
    bootstrap_storage(str(tmp_path / "mystmon.db"), str(tmp_path / "latest.json"), str(tmp_path / "snmp_extend.txt"))
    store = HistoryStore(str(tmp_path / "mystmon.db"), timezone_name="Asia/Kolkata")

    assert store.report_sent("2026-05-25") is False
    store.record_report("2026-05-25", 24, "sent", "message")

    assert store.report_sent("2026-05-25") is True


def test_history_skips_unreachable_placeholders_when_portal_nodes_exist(tmp_path) -> None:
    bootstrap_storage(str(tmp_path / "mystmon.db"), str(tmp_path / "latest.json"), str(tmp_path / "snmp_extend.txt"))
    store = HistoryStore(str(tmp_path / "mystmon.db"), timezone_name="Asia/Kolkata")
    snapshot = _snapshot(datetime(2026, 5, 25, 3, 0, tzinfo=UTC), earnings=12.5, quality=2.5)
    snapshot["nodes"].append(
        {
            "name": "unreachable-remote-host",
            "host": "remote-host-2",
            "running": False,
            "restart_count": 0,
            "uptime_seconds": 0,
            "log_counts": {"error_or_warning": 1},
        }
    )

    store.append_snapshot(snapshot)
    delta = store.delta(hours=24)

    assert delta["fleet"]["current"]["nodes"] == 1.0
    assert [node["node_name"] for node in delta["nodes"]] == ["Node One"]


def test_history_counts_local_running_nodes_without_portal_online(tmp_path) -> None:
    bootstrap_storage(str(tmp_path / "mystmon.db"), str(tmp_path / "latest.json"), str(tmp_path / "snmp_extend.txt"))
    store = HistoryStore(str(tmp_path / "mystmon.db"), timezone_name="Asia/Kolkata")
    snapshot = {
        "generated_at": datetime(2026, 5, 25, 3, 0, tzinfo=UTC).isoformat(),
        "collection_counts": {"myst": 1, "mystnodes": 0, "prometheus": 0, "snmp": 0},
        "nodes": [
            {
                "name": "myst",
                "host": "example-host",
                "running": True,
                "restart_count": 0,
                "uptime_seconds": 100,
                "log_counts": {"error_or_warning": 0},
            }
        ],
        "mystnodes": {"endpoints": {}, "node_details": {"nodes": {}}, "local_matches": {}},
    }

    store.append_snapshot(snapshot)
    delta = store.delta(hours=24)
    latest_nodes = store.nodes()

    assert delta["fleet"]["current"]["nodes"] == 1.0
    assert delta["fleet"]["current"]["running"] == 1.0
    assert delta["fleet"]["current"]["online"] is None
    assert delta["nodes"][0]["current"]["running"] == 1.0
    assert delta["nodes"][0]["current"]["online"] is None
    assert latest_nodes["nodes"][0]["running"] == 1.0
    assert latest_nodes["nodes"][0]["online"] is None


def test_history_overall_preserves_unknown_portal_metrics(tmp_path) -> None:
    bootstrap_storage(str(tmp_path / "mystmon.db"), str(tmp_path / "latest.json"), str(tmp_path / "snmp_extend.txt"))
    store = HistoryStore(str(tmp_path / "mystmon.db"), timezone_name="Asia/Kolkata")
    snapshot = {
        "generated_at": datetime(2026, 5, 25, 3, 0, tzinfo=UTC).isoformat(),
        "collection_counts": {"myst": 1, "mystnodes": 0, "prometheus": 0, "snmp": 0},
        "nodes": [
            {
                "name": "myst",
                "host": "example-host",
                "running": True,
                "restart_count": 0,
                "uptime_seconds": 100,
                "log_counts": {"error_or_warning": 0},
            }
        ],
        "mystnodes": {"endpoints": {}, "node_details": {"nodes": {}}, "local_matches": {}},
    }

    store.append_snapshot(snapshot)
    overall = store.overall()

    assert overall["collections"][0]["fleet"]["online"] is None
    assert overall["collections"][0]["fleet"]["earnings_total"] is None
    assert overall["collections"][0]["fleet"]["quality_avg"] is None


def test_history_exposes_overall_and_node_sqlite_views(tmp_path) -> None:
    bootstrap_storage(str(tmp_path / "mystmon.db"), str(tmp_path / "latest.json"), str(tmp_path / "snmp_extend.txt"))
    store = HistoryStore(str(tmp_path / "mystmon.db"), timezone_name="Asia/Kolkata")
    store.append_snapshot(_snapshot(datetime(2026, 5, 24, 2, 0, tzinfo=UTC), earnings=10.0, quality=2.0))
    store.append_snapshot(_snapshot(datetime(2026, 5, 25, 3, 0, tzinfo=UTC), earnings=12.5, quality=2.5))

    overall = store.overall(limit=10)
    latest_nodes = store.nodes()
    all_node_rows = store.nodes(latest_only=False, limit=10)
    node_history = store.node("Node", limit=10)

    assert overall["count"] == 2
    assert overall["collections"][0]["fleet"]["earnings_total"] == 12.5
    assert latest_nodes["count"] == 1
    assert latest_nodes["nodes"][0]["node_name"] == "Node One"
    assert all_node_rows["count"] == 2
    assert node_history["count"] == 2
    assert node_history["history"][0]["earnings_total"] == 12.5


def test_history_public_nodes_include_known_flags(tmp_path) -> None:
    bootstrap_storage(str(tmp_path / "mystmon.db"), str(tmp_path / "latest.json"), str(tmp_path / "snmp_extend.txt"))
    store = HistoryStore(str(tmp_path / "mystmon.db"), timezone_name="Asia/Kolkata")
    store.append_snapshot(_snapshot(datetime(2026, 5, 25, 3, 0, tzinfo=UTC), earnings=12.5, quality=2.5))

    latest_nodes = store.nodes()
    node = latest_nodes["nodes"][0]

    assert node["quality_known"] is True
    assert node["earnings_known"] is True
    assert node["uptime_known"] is True


def test_history_public_nodes_include_tequilapi_fields(tmp_path) -> None:
    bootstrap_storage(str(tmp_path / "mystmon.db"), str(tmp_path / "latest.json"), str(tmp_path / "snmp_extend.txt"))
    store = HistoryStore(str(tmp_path / "mystmon.db"), timezone_name="Asia/Kolkata")
    snapshot = _snapshot(datetime(2026, 5, 25, 3, 0, tzinfo=UTC), earnings=12.5, quality=2.5)
    snapshot["nodes"][0]["api"] = {
        "enabled": True,
        "up": True,
        "schema_available": True,
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
            "services": {"services": {"count": 6, "running_count": 6, "types": ["dvpn"]}},
            "sessions": {
                "sessions": {"daily": {"count": 42}},
                "session_stats_aggregated": {"daily": {"count": 817}},
            },
            "provider": {"provider_quality": {"quality": 1.7}},
            "payments": {"transactor_fees_v2": {"current": {"settlement": {"human": "0.033706"}}}},
        },
    }
    store.append_snapshot(snapshot)

    node = store.nodes()["nodes"][0]

    assert node["api_public_ip"] == "122.179.195.76"
    assert node["api_location_city"] == "Ghaziabad"
    assert node["api_nat_type"] == "prcone"
    assert node["api_services_running"] == 6
    assert node["api_sessions_1d"] == 817
    assert node["api_provider_quality"] == 1.7


def test_history_persists_and_returns_local_timezone_timestamps(tmp_path) -> None:
    bootstrap_storage(str(tmp_path / "mystmon.db"), str(tmp_path / "latest.json"), str(tmp_path / "snmp_extend.txt"))
    store = HistoryStore(str(tmp_path / "mystmon.db"), timezone_name="Asia/Kolkata")
    snapshot = _snapshot(datetime(2026, 5, 25, 3, 0, tzinfo=UTC), earnings=12.5, quality=2.5)

    store.append_snapshot(snapshot)

    latest = store.latest_collection()
    node = store.nodes()["nodes"][0]

    assert latest is not None
    assert latest["collected_at"] == "2026-05-25T08:30:00+05:30"
    assert node["collected_at"] == "2026-05-25T08:30:00+05:30"


def _snapshot(collected_at: datetime, earnings: float, quality: float, warnings: int = 0) -> dict:
    return {
        "generated_at": collected_at.isoformat(),
        "collection_counts": {"myst": 1, "mystnodes": 5, "prometheus": 0, "snmp": 0},
        "nodes": [
            {
                "name": "myst.1.x",
                "host": "example-host",
                "running": True,
                "restart_count": 0,
                "uptime_seconds": 100,
                "log_counts": {"error_or_warning": warnings, "identity_warning": 0, "promise": 1, "session": 2},
            }
        ],
        "mystnodes": {
            "endpoints": {
                "nodes": {
                    "data": {
                        "nodes": [
                            {
                                "id": "node-1",
                                "name": "Node One",
                                "identity": "0xabc",
                                "localIp": "example-local-ip",
                                "nodeStatus": {"online": True, "quality": quality},
                                "earnings": [{"etherAmount": earnings}],
                            }
                        ]
                    }
                }
            },
            "node_details": {
                "nodes": {
                    "node-1": {
                        "detail": {"data": {"uptimeMinLast24H": 1440}},
                    }
                }
            },
            "local_matches": {
                "node-1": {
                    "container_name": "myst.1.x",
                    "host": "example-host",
                }
            },
        },
    }
