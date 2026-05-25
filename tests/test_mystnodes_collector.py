from mystmon.collectors.mystnodes import _match_local_nodes


def test_match_local_nodes_uses_portal_local_ip() -> None:
    matches = _match_local_nodes(
        [
            {
                "id": "portal-1",
                "name": "node-one",
                "localIp": "192.168.12.71",
            }
        ],
        [
            {
                "name": "myst.12.x",
                "container_name": "myst.12.x",
                "host": "192.168.1.72",
                "running": True,
                "status": "running",
                "restart_count": 0,
                "uptime_seconds": 120,
                "networks": [{"name": "ipvlan12", "ip_address": "192.168.12.71"}],
                "log_counts": {"error_or_warning": 2},
                "warnings": ["failed to sign metrics"],
            }
        ],
    )

    assert matches["portal-1"]["container_name"] == "myst.12.x"
    assert matches["portal-1"]["running"] is True
    assert matches["portal-1"]["log_counts"]["error_or_warning"] == 2
