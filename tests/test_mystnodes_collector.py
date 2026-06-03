from mystmon.collectors.mystnodes import _match_local_nodes


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
