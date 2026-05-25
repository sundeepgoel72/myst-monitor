from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from mystmon.config import TelegramConfig
from mystmon.telegram import format_daily_report, next_report_delay


def test_format_daily_report_includes_earnings_and_variations() -> None:
    message = format_daily_report(
        {
            "ok": True,
            "hours": 24,
            "latest": {"collected_at": "2026-05-25T02:30:00+00:00"},
            "fleet": {
                "current": {
                    "nodes": 8.0,
                    "online": 7.0,
                    "earnings_total": 12.5,
                    "quality_avg": 2.25,
                    "restart_count": 1.0,
                    "log_error_or_warning": 4.0,
                },
                "delta": {
                    "online": -1.0,
                    "earnings_total": 2.5,
                    "quality_avg": -0.2,
                    "restart_count": 1.0,
                    "log_error_or_warning": 3.0,
                },
            },
            "nodes": [
                {
                    "node_name": "Node One",
                    "current": {"online": 1.0},
                    "delta": {"earnings_total": 2.5, "quality": -0.1, "restart_count": 0, "log_error_or_warning": 0},
                },
                {
                    "node_name": "Node Two",
                    "current": {"online": 0.0},
                    "delta": {"earnings_total": 0.0, "quality": 0, "restart_count": 1.0, "log_error_or_warning": 3.0},
                },
            ],
        },
        "mystmon-dev",
    )

    assert "Fleet earnings: 12.500000 (+2.500000)" in message
    assert "Avg quality: 2.25 (-0.20)" in message
    assert "Per-node:" in message
    assert "Node One: online, earn unknown (+2.500000), quality unknown (-0.10)" in message
    assert "Node Two: offline" in message
    assert "Attention:" in message


def test_next_report_delay_uses_configured_local_time() -> None:
    config = TelegramConfig(report_time_local="08:00", timezone="Asia/Kolkata")
    now = datetime(2026, 5, 25, 7, 30, tzinfo=ZoneInfo("Asia/Kolkata"))

    assert next_report_delay(config, now=now) == 1800
