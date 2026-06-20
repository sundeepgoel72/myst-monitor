from __future__ import annotations

import logging
from pathlib import Path

from mystmon.main import LocalTimezoneFormatter


def test_local_timezone_formatter_uses_configured_timezone() -> None:
    formatter = LocalTimezoneFormatter("%(asctime)s %(message)s", "Asia/Kolkata")
    record = logging.LogRecord(
        name="mystmon.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.created = 1760952994.443799  # 2025-10-20T09:36:34.443799+00:00

    rendered = formatter.format(record)

    assert rendered.startswith("2025-10-20T15:06:34.443+05:30 hello")


def test_local_timezone_formatter_honors_date_format() -> None:
    formatter = LocalTimezoneFormatter("%(asctime)s", "Asia/Kolkata")
    record = logging.LogRecord(
        name="mystmon.test",
        level=logging.INFO,
        pathname=str(Path(__file__)),
        lineno=24,
        msg="",
        args=(),
        exc_info=None,
    )
    record.created = 1760952994.0

    rendered = formatter.formatTime(record, "%Y-%m-%d %H:%M:%S %z")

    assert rendered == "2025-10-20 15:06:34 +0530"
