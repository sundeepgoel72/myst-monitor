from __future__ import annotations

import html
import os
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from mystmon.config import TelegramConfig
from mystmon.history import HistoryStore


class TelegramNotifier:
    def __init__(self, config: TelegramConfig, history: HistoryStore | None, service_name: str) -> None:
        self.config = config
        self.history = history
        self.service_name = service_name

    async def send_test(self) -> dict[str, Any]:
        message = f"<b>MystMon test</b>\n{html.escape(self.service_name)} Telegram integration is configured."
        return await self.send_message(message)

    async def send_report(self, hours: int = 24, force: bool = False) -> dict[str, Any]:
        if self.history is None:
            return {"ok": False, "reason": "history_disabled"}
        now_local = datetime.now(ZoneInfo(self.config.timezone))
        report_date = now_local.date().isoformat()
        if not force and self.history.report_sent(report_date):
            return {"ok": True, "skipped": True, "reason": "already_sent", "report_date": report_date}
        delta = self.history.delta(hours=hours)
        message = format_daily_report(delta, self.service_name, hours)
        result = await self.send_message(message)
        self.history.record_report(report_date, hours, "sent" if result.get("ok") else "failed", message)
        return {"ok": bool(result.get("ok")), "report_date": report_date, "telegram": result}

    async def send_message(self, message: str) -> dict[str, Any]:
        token = os.getenv(self.config.bot_token_env, "")
        chat_id = os.getenv(self.config.chat_id_env, "")
        if not token or not chat_id:
            return {"ok": False, "reason": "missing_telegram_env"}
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_notification": self.config.disable_notification,
                },
            )
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        return {"ok": response.is_success and bool(data.get("ok", True)), "status_code": response.status_code, "data": data}


def next_report_delay(config: TelegramConfig, now: datetime | None = None) -> float:
    zone = ZoneInfo(config.timezone)
    current = now.astimezone(zone) if now else datetime.now(zone)
    hour, minute = [int(part) for part in config.report_time_local.split(":", 1)]
    target = datetime.combine(current.date(), time(hour, minute), tzinfo=zone)
    if target <= current:
        target += timedelta(days=1)
    return max(0.0, (target - current).total_seconds())


def format_daily_report(delta: dict[str, Any], service_name: str, hours: int = 24) -> str:
    if not delta.get("ok"):
        return f"<b>MystMon daily report</b>\n{html.escape(service_name)} has no collection history yet."
    fleet = delta.get("fleet") or {}
    current = fleet.get("current") or {}
    changes = fleet.get("delta") or {}
    latest = delta.get("latest") or {}
    lines = [
        "<b>MystMon daily report</b>",
        f"{html.escape(service_name)} · last {hours}h",
        f"Snapshot: {html.escape(str(latest.get('collected_at', 'unknown')))}",
        "",
        f"Fleet earnings: {_fmt(current.get('earnings_total'), 6)} ({_signed(changes.get('earnings_total'), 6)})",
        f"Online nodes: {_fmt(current.get('online'), 0)} / {_fmt(current.get('nodes'), 0)} ({_signed(changes.get('online'), 0)})",
        f"Avg quality: {_fmt(current.get('quality_avg'), 2)} ({_signed(changes.get('quality_avg'), 2)})",
        f"Restarts: {_fmt(current.get('restart_count'), 0)} ({_signed(changes.get('restart_count'), 0)})",
        f"Warnings/errors: {_fmt(current.get('log_error_or_warning'), 0)} ({_signed(changes.get('log_error_or_warning'), 0)})",
        "",
    ]
    notable = _notable_nodes(delta.get("nodes") or [])
    lines.extend(notable if notable else ["No notable node changes."])
    return "\n".join(lines)


def _notable_nodes(nodes: list[dict[str, Any]]) -> list[str]:
    earnings = sorted(
        nodes,
        key=lambda node: _number((node.get("delta") or {}).get("earnings_total")),
        reverse=True,
    )[:5]
    lines = ["Top earnings changes:"]
    for node in earnings:
        change = (node.get("delta") or {}).get("earnings_total")
        if change == "unknown" or _number(change) == 0:
            continue
        lines.append(f"- {html.escape(str(node.get('node_name')))}: {_signed(change, 6)}")
    alerts: list[str] = []
    for node in nodes:
        current = node.get("current") or {}
        changes = node.get("delta") or {}
        reasons = []
        if current.get("online") == 0:
            reasons.append("offline")
        if _number(changes.get("quality")) < 0:
            reasons.append(f"quality {_signed(changes.get('quality'), 2)}")
        if _number(changes.get("restart_count")) > 0:
            reasons.append(f"restarts {_signed(changes.get('restart_count'), 0)}")
        if _number(changes.get("log_error_or_warning")) > 0:
            reasons.append(f"warnings {_signed(changes.get('log_error_or_warning'), 0)}")
        if reasons:
            alerts.append(f"- {html.escape(str(node.get('node_name')))}: {', '.join(reasons)}")
    if alerts:
        lines.append("")
        lines.append("Attention:")
        lines.extend(alerts[:8])
    return lines


def _fmt(value: Any, digits: int) -> str:
    if value is None or value == "unknown":
        return "unknown"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "unknown"


def _signed(value: Any, digits: int) -> str:
    if value == "unknown" or value is None:
        return "unknown"
    number = _number(value)
    return f"{number:+.{digits}f}"


def _number(value: Any) -> float:
    try:
        if value == "unknown" or value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
