from mystmon.collectors.myst import _node_display_name, extract_api_metrics, summarize_logs


def test_summarize_logs_tracks_myst_health_patterns() -> None:
    summary = summarize_logs(
        "\n".join(
            [
                "Received hermes promise",
                "promise state updated",
                "session started",
                "failed to sign metrics",
                "authentication needed: password or unlock",
            ]
        )
    )

    assert summary["promise"] == 2
    assert summary["session"] == 1
    assert summary["identity_warning"] == 2
    assert summary["error_or_warning"] == 2


def test_extract_api_metrics_from_documented_healthcheck() -> None:
    extracted = extract_api_metrics(
        "healthcheck",
        "health",
        {
            "uptime": "9h43m30.17653267s",
            "process": 1,
            "version": "1.35.4",
            "build_info": {
                "commit": "5baa18a2",
                "branch": "1.35.4",
                "build_number": "16167610008",
            },
        },
    )

    assert extracted["metrics"]["health_up"] == 1
    assert extracted["metrics"]["health_uptime_seconds"] == 35010
    assert extracted["metrics"]["health_process"] == 1
    assert extracted["labels"]["health_version"] == "1.35.4"


def test_extract_api_metrics_from_documented_lists() -> None:
    identities = extract_api_metrics("identities", "identities", {"identities": [{"id": "0x1"}]})
    services = extract_api_metrics(
        "services",
        "services",
        [{"type": "wireguard", "status": "running"}, {"type": "scraping", "status": "stopped"}],
    )

    assert identities["metrics"]["identities_count"] == 1
    assert services["metrics"]["services_count"] == 2
    assert services["metrics"]["services_running_count"] == 1


def test_node_display_name_prefers_api_identity() -> None:
    name = _node_display_name(
        "myst.1.x",
        {
            "identity": "0xabc123",
            "labels": {"node_id": "node-from-label"},
        },
    )

    assert name == "0xabc123"


def test_node_display_name_falls_back_to_container_name() -> None:
    assert _node_display_name("myst.1.x", {"labels": {}}) == "myst.1.x"
