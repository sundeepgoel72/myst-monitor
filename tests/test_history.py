from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mystmon.history import HistoryStore


def test_history_appends_snapshots_and_calculates_delta(tmp_path) -> None:
    store = HistoryStore(str(tmp_path / "mystmon.db"))
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
    assert delta["fleet"]["delta"]["log_error_or_warning"] == 3.0
    assert delta["nodes"][0]["delta"]["earnings_total"] == 2.5


def test_history_missing_prior_values_are_unknown(tmp_path) -> None:
    store = HistoryStore(str(tmp_path / "mystmon.db"))
    store.append_snapshot(_snapshot(datetime(2026, 5, 25, 3, 0, tzinfo=UTC), earnings=12.5, quality=2.5))

    delta = store.delta(hours=24)

    assert delta["prior"] is None
    assert delta["fleet"]["delta"]["earnings_total"] == "unknown"
    assert delta["nodes"][0]["delta"]["quality"] == "unknown"


def test_report_records_prevent_duplicates(tmp_path) -> None:
    store = HistoryStore(str(tmp_path / "mystmon.db"))

    assert store.report_sent("2026-05-25") is False
    store.record_report("2026-05-25", 24, "sent", "message")

    assert store.report_sent("2026-05-25") is True


def test_history_skips_unreachable_placeholders_when_portal_nodes_exist(tmp_path) -> None:
    store = HistoryStore(str(tmp_path / "mystmon.db"))
    snapshot = _snapshot(datetime(2026, 5, 25, 3, 0, tzinfo=UTC), earnings=12.5, quality=2.5)
    snapshot["nodes"].append(
        {
            "name": "unreachable-192.168.1.174",
            "host": "192.168.1.174",
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


def _snapshot(collected_at: datetime, earnings: float, quality: float, warnings: int = 0) -> dict:
    return {
        "generated_at": collected_at.isoformat(),
        "collection_counts": {"myst": 1, "mystnodes": 5, "prometheus": 0, "snmp": 0},
        "nodes": [
            {
                "name": "myst.1.x",
                "host": "192.168.1.72",
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
                                "localIp": "192.168.1.72",
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
                    "host": "192.168.1.72",
                }
            },
        },
    }
