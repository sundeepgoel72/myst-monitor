from pathlib import Path

from prometheus_client import CollectorRegistry, Gauge, generate_latest
from mystmon.api import _set_portal_metrics
from mystmon.api import create_app
from mystmon.config import MystMonConfig


def test_create_app_imports_collectors(tmp_path: Path) -> None:
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
        }
    )
    app = create_app(config)

    assert app.title == "MystMon API"


def test_portal_metrics_include_quality_and_earnings() -> None:
    registry = CollectorRegistry()
    summary = Gauge("summary", "summary", ["metric"], registry=registry)
    online = Gauge("online", "online", ["node_id", "name", "identity", "local_ip"], registry=registry)
    quality = Gauge("quality", "quality", ["node_id", "name", "identity", "local_ip"], registry=registry)
    earnings = Gauge("earnings", "earnings", ["node_id", "name", "identity", "local_ip"], registry=registry)
    uptime = Gauge("uptime", "uptime", ["node_id", "name", "identity", "local_ip"], registry=registry)
    local_match = Gauge("local_match", "local_match", ["node_id", "name", "local_ip", "container", "host"], registry=registry)

    _set_portal_metrics(
        {
            "endpoints": {
                "me": {"data": {"nodesInfo": {"totalCount": 1, "onlineCount": 1}}},
                "total_earnings": {"data": {"earningsTotal": 12.5}},
                "total_transferred": {"data": {"transferredTotal": 99}},
                "nodes": {
                    "data": {
                        "nodes": [
                            {
                                "id": "n1",
                                "name": "node-one",
                                "identity": "0xabc",
                                "localIp": "example-local-ip",
                                "nodeStatus": {"online": True, "quality": 2.6},
                                "earnings": [{"etherAmount": "1.25"}, {"etherAmount": "2"}],
                            }
                        ]
                    }
                },
            },
            "node_details": {"nodes": {"n1": {"detail": {"data": {"uptimeMinLast24H": 1436}}}}},
            "local_matches": {"n1": {"container_name": "myst.1.x", "host": "example-host"}},
        },
        summary,
        online,
        quality,
        earnings,
        uptime,
        local_match,
    )

    metrics = generate_latest(registry).decode()

    assert 'summary{metric="nodes_total"} 1.0' in metrics
    assert 'quality{identity="0xabc",local_ip="example-local-ip",name="node-one",node_id="n1"} 2.6' in metrics
    assert 'earnings{identity="0xabc",local_ip="example-local-ip",name="node-one",node_id="n1"} 3.25' in metrics
    assert 'uptime{identity="0xabc",local_ip="example-local-ip",name="node-one",node_id="n1"} 1436.0' in metrics
