from mystmon.snapshot import build_snapshot, render_snmp_extend


def test_render_snmp_extend_uses_compact_node_status() -> None:
    rendered = render_snmp_extend(
        {
            "generated_at": "2026-05-23T00:00:00+00:00",
            "nodes": [
                {
                    "name": "myst.16.x",
                    "running": True,
                    "restart_count": 2,
                    "uptime_seconds": 3600,
                    "log_counts": {
                        "error_or_warning": 1,
                        "promise": 3,
                        "session": 4,
                        "identity_warning": 0,
                    },
                    "api": {
                        "up": True,
                        "endpoints": {"healthcheck": {"ok": True}},
                        "metrics": {"health_uptime_seconds": 30},
                    },
                }
            ],
        }
    )

    assert "node_count=1" in rendered
    assert "myst_16_x.running=1" in rendered
    assert "myst_16_x.promises=3" in rendered
    assert "myst_16_x.api_up=1" in rendered
    assert "myst_16_x.api.health_uptime_seconds=30" in rendered
    assert "myst_16_x.api_endpoint.healthcheck=1" in rendered


def test_snapshot_can_include_mystnodes_portal() -> None:
    snapshot = build_snapshot(
        [],
        {"myst": 0, "mystnodes": 1},
        {"authenticated": True, "endpoints": {"me": {"ok": True}}},
    )
    rendered = render_snmp_extend(snapshot)

    assert snapshot["mystnodes"]["authenticated"] is True
    assert "mystnodes.authenticated=1" in rendered
    assert "mystnodes.endpoint_count=1" in rendered
