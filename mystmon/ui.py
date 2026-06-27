from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from mystmon import __version__
from mystmon.config import MystMonConfig
from mystmon.history import HistoryStore
from mystmon.scheduler import CollectorScheduler
from mystmon.storage import ReadingStore
from mystmon.telegram import TelegramNotifier


def create_ui_router(
    config: MystMonConfig,
    store: ReadingStore,
    history: HistoryStore | None,
    telegram: TelegramNotifier,
    scheduler: CollectorScheduler,
) -> APIRouter:
    router = APIRouter()
    templates_dir = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    def _base_context(request: Request) -> dict[str, Any]:
        return {
            "request": request,
            "config": config,
            "service_name": config.service.name,
            "ui_path": config.ui.path.rstrip("/"),
            "version": __version__,
        }

    @router.get(config.ui.path, response_class=HTMLResponse, include_in_schema=False)
    async def dashboard(request: Request) -> Response:
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            _base_context(request) | {"page": "dashboard"},
        )

    @router.get(f"{config.ui.path}/fleet", response_class=HTMLResponse, include_in_schema=False)
    async def fleet(request: Request) -> Response:
        return templates.TemplateResponse(
            request,
            "fleet.html",
            _base_context(request) | {"page": "fleet"},
        )

    @router.get(f"{config.ui.path}/node/{{node_key}}", response_class=HTMLResponse, include_in_schema=False)
    async def node_detail(request: Request, node_key: str) -> Response:
        return templates.TemplateResponse(
            request,
            "node_detail.html",
            _base_context(request) | {"page": "node", "node_key": node_key},
        )

    @router.get(f"{config.ui.path}/history", response_class=HTMLResponse, include_in_schema=False)
    async def history_view(request: Request) -> Response:
        return templates.TemplateResponse(
            request,
            "history.html",
            _base_context(request) | {"page": "history"},
        )

    @router.get(f"{config.ui.path}/settings", response_class=HTMLResponse, include_in_schema=False)
    async def settings(request: Request) -> Response:
        return templates.TemplateResponse(
            request,
            "settings.html",
            _base_context(request) | {"page": "settings"},
        )

    # API endpoints for UI consumption
    @router.get("/api/v1/ui/config", include_in_schema=False)
    async def ui_config() -> dict[str, Any]:
        return {
            "auto_refresh_interval_seconds": config.ui.auto_refresh_interval_seconds,
            "max_history_points": config.ui.max_history_points,
            "theme": config.ui.theme,
            "service_name": config.service.name,
        }

    @router.get("/api/v1/ui/home", include_in_schema=False)
    async def ui_home() -> dict[str, Any]:
        if not history:
            return {"ok": False, "reason": "history_disabled"}

        latest = history._record_query("SELECT * FROM collections ORDER BY collected_at DESC, id DESC LIMIT 1")
        if latest is None:
            return {"ok": True, "wallet": {"total": None, "accounts": []}, "nodes": [], "collection": None}

        snapshot = latest.snapshot or {}
        mystnodes = snapshot.get("mystnodes") or {}
        accounts = mystnodes.get("accounts") or []
        nodes = [
            _public_home_node(row)
            for row in history._nodes_for_collection(latest.id).values()
        ]
        nodes.sort(key=lambda row: (str(row.get("node_name") or row.get("node_key") or "").lower(), str(row.get("node_key") or "").lower()))

        return {
            "ok": True,
            "collection": {"id": latest.id, "collected_at": latest.collected_at.isoformat()},
            "wallet": _wallet_summary(accounts),
            "nodes": nodes,
        }

    @router.get("/api/v1/collectors/status", include_in_schema=False)
    async def collectors_status() -> dict[str, Any]:
        snapshot_path = Path(config.outputs.latest_json_path)
        collector_status = {
            "myst": _collector_status(enabled=config.myst.enabled),
            "mystnodes": _collector_status(enabled=bool(config.mystnodes_accounts)),
            "prometheus": _collector_status(enabled=config.prometheus.enabled and bool(config.prometheus.targets)),
            "snmp": _collector_status(enabled=config.snmp.enabled and bool(config.snmp.targets)),
        }
        if snapshot_path.exists():
            try:
                content = snapshot_path.read_text(encoding="utf-8")
                if content.strip():
                    snapshot = json.loads(content)
                    counts = snapshot.get("collection_counts", {})
                    for source, count in counts.items():
                        existing = collector_status.get(source, _collector_status(enabled=True))
                        enabled = existing.get("enabled", True)
                        collector_status[source] = {
                            "enabled": enabled,
                            "last_run": snapshot.get("generated_at"),
                            "nodes_collected": count,
                            "status": _collector_run_status(enabled=enabled, count=count),
                        }
            except Exception:
                # Log error but don't fail the endpoint
                pass
        return {"collectors": collector_status}

    @router.get("/api/v1/system/info", include_in_schema=False)
    async def system_info() -> dict[str, Any]:
        import sqlite3

        info = {
            "version": __version__,
            "service_name": config.service.name,
            "uptime_seconds": 0,
            "database": {"enabled": config.history.enabled},
            "disk_usage": {},
        }

        if config.history.enabled and history:
            try:
                db_path = Path(config.history.db_path)
                if db_path.exists():
                    stat = db_path.stat()
                    info["database"]["size_bytes"] = stat.st_size
                    info["database"]["path"] = str(db_path)

                    with sqlite3.connect(db_path) as db:
                        db.row_factory = sqlite3.Row
                        row = db.execute("SELECT COUNT(*) as cnt FROM collections").fetchone()
                        info["database"]["collections"] = row["cnt"] if row else 0
                        row = db.execute("SELECT COUNT(*) as cnt FROM node_metrics").fetchone()
                        info["database"]["node_metrics"] = row["cnt"] if row else 0
                        row = db.execute(
                            "SELECT MIN(collected_at) as min_dt, MAX(collected_at) as max_dt FROM collections"
                        ).fetchone()
                        if row and row["min_dt"]:
                            info["database"]["date_range"] = {
                                "from": row["min_dt"],
                                "to": row["max_dt"],
                            }
            except Exception as e:
                info["database"]["error"] = str(e)

        try:
            data_dir = Path(config.service.data_dir)
            if data_dir.exists():
                import shutil
                usage = shutil.disk_usage(data_dir)
                info["disk_usage"] = {
                    "total_bytes": usage.total,
                    "used_bytes": usage.used,
                    "free_bytes": usage.free,
                    "path": str(data_dir),
                }
        except Exception:
            pass

        return info

    @router.get("/api/v1/history/export", include_in_schema=False)
    async def history_export(format: str = "json", hours: int = 24) -> Response:
        if not history:
            return Response(content="History disabled", status_code=400)

        from datetime import UTC, datetime, timedelta
        target = datetime.now(UTC) - timedelta(hours=hours)
        latest = history._record_query("SELECT * FROM collections ORDER BY collected_at DESC, id DESC LIMIT 1")
        if not latest:
            return Response(content="No data", status_code=404)

        prior = history._record_query(
            "SELECT * FROM collections WHERE collected_at <= ? ORDER BY collected_at DESC, id DESC LIMIT 1",
            (target.isoformat(),),
        )

        latest_nodes = history._nodes_for_collection(latest.id)
        prior_nodes = history._nodes_for_collection(prior.id) if prior else {}

        if format == "csv":
            import csv
            from io import StringIO

            output = StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "node_key", "node_name", "identity", "local_ip", "host", "container_name",
                "current_online", "current_quality", "current_earnings_total", "current_restart_count",
                "prior_online", "prior_quality", "prior_earnings_total", "prior_restart_count",
                "delta_online", "delta_quality", "delta_earnings_total", "delta_restart_count",
            ])
            for key, node in sorted(latest_nodes.items()):
                prior_node = prior_nodes.get(key)
                writer.writerow([
                    key,
                    node.get("node_name", ""),
                    node.get("identity", ""),
                    node.get("local_ip", ""),
                    node.get("host", ""),
                    node.get("container_name", ""),
                    node.get("online"),
                    node.get("quality"),
                    node.get("earnings_total"),
                    node.get("restart_count"),
                    prior_node.get("online") if prior_node else "",
                    prior_node.get("quality") if prior_node else "",
                    prior_node.get("earnings_total") if prior_node else "",
                    prior_node.get("restart_count") if prior_node else "",
                    _csv_delta(node.get("online"), prior_node.get("online")) if prior_node else "",
                    _csv_delta(node.get("quality"), prior_node.get("quality")) if prior_node else "",
                    _csv_delta(node.get("earnings_total"), prior_node.get("earnings_total")) if prior_node else "",
                    _csv_delta(node.get("restart_count"), prior_node.get("restart_count")) if prior_node else "",
                ])
            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=mystmon_export_{hours}h.csv"},
            )

        return {
            "hours": hours,
            "latest": {"id": latest.id, "collected_at": latest.collected_at.isoformat()},
            "prior": {"id": prior.id, "collected_at": prior.collected_at.isoformat()} if prior else None,
            "nodes": [
                {
                    "node_key": key,
                    "current": node,
                    "prior": prior_nodes.get(key),
                }
                for key, node in sorted(latest_nodes.items())
            ],
        }

    return router


def _collector_status(*, enabled: bool) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "last_run": None,
        "nodes_collected": 0,
        "status": "pending" if enabled else "disabled",
    }



def _public_home_node(row: dict[str, Any]) -> dict[str, Any]:
    quality = row.get("quality")
    earnings_total = row.get("earnings_total")
    running = row.get("running")
    online = row.get("online")
    return {
        "node_key": row.get("node_key") or row.get("identity") or row.get("node_name"),
        "node_name": row.get("node_name") or row.get("container_name") or row.get("host"),
        "identity": row.get("identity"),
        "status": _home_status_label(online, running),
        "running": running,
        "online": online,
        "quality": quality,
        "quality_known": quality is not None,
        "earnings_total": earnings_total,
        "earnings_known": earnings_total is not None,
        "restart_count": row.get("restart_count"),
        "last_seen": row.get("collected_at"),
    }


def _home_status_label(online: Any, running: Any) -> str:
    if online == 1 or online is True:
        return "Online"
    if online == 0 or online is False:
        return "Offline"
    if running == 1 or running is True:
        return "Running"
    if running == 0 or running is False:
        return "Stopped"
    return "Unknown"


def _wallet_summary(accounts: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    total_value = 0.0
    total_known = False
    seen_wallets: set[str] = set()
    for account in accounts:
        endpoints = account.get("endpoints") or {}
        wallet_endpoint = endpoints.get("wallet_balance")
        amount_text = _wallet_amount_text(wallet_endpoint)
        amount_value = _wallet_amount_value(amount_text)
        wallet_key = str(account.get("wallet_address_hint") or account.get("wallet_address") or account.get("name") or "")
        if amount_value is not None and wallet_key not in seen_wallets:
            total_value += amount_value
            total_known = True
            seen_wallets.add(wallet_key)
        rows.append(
            {
                "name": account.get("name"),
                "wallet_address_hint": account.get("wallet_address_hint"),
                "wallet_total": amount_text,
            }
        )
    return {
        "total": str(total_value) if total_known else None,
        "accounts": rows,
    }


def _wallet_amount_text(endpoint: Any) -> str | None:
    if not isinstance(endpoint, dict) or endpoint.get("ok") is False:
        return None
    data = endpoint.get("data")
    if isinstance(data, dict):
        summary = data.get("summary")
        if summary not in (None, ""):
            return str(summary)
        for path in (
            ("balance",),
            ("availableBalance",),
            ("current", "balance"),
            ("current", "settlement", "human"),
            ("current", "settlement", "amount"),
        ):
            value = data
            for key in path:
                if not isinstance(value, dict) or key not in value:
                    value = None
                    break
                value = value[key]
            if value not in (None, ""):
                return str(value)
    elif data not in (None, ""):
        return str(data)
    return None


def _wallet_amount_value(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    import re

    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", str(value))
    if not match:
        return None
    token = match.group(0).replace(',', '')
    try:
        return float(token)
    except ValueError:
        return None


def _csv_delta(current: Any, prior: Any) -> float | str:
    if current is None or current == "" or prior is None or prior == "":
        return ""
    try:
        return float(current) - float(prior)
    except (TypeError, ValueError):
        return ""


def _collector_run_status(*, enabled: bool, count: Any) -> str:
    if not enabled:
        return "disabled"
    try:
        return "ok" if float(count) > 0 else "warning"
    except (TypeError, ValueError):
        return "warning"
