from mystmon.collectors.myst import summarize_logs


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
