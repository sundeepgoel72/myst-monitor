from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "Asia/Kolkata"


def app_timezone(timezone_name: str | None = None) -> ZoneInfo:
    return ZoneInfo(timezone_name or DEFAULT_TIMEZONE)


def now_local(timezone_name: str | None = None) -> datetime:
    return datetime.now(app_timezone(timezone_name))


def parse_time(value: Any, timezone_name: str | None = None) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(app_timezone(timezone_name))
