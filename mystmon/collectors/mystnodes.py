from __future__ import annotations

import logging
import os
from urllib.parse import urlencode
from typing import Any

import httpx

from mystmon.config import MystNodesPortalConfig, MystNodesPortalEndpointConfig
from mystmon.collectors.myst import _redact_api_value

LOGGER = logging.getLogger(__name__)


async def collect_mystnodes_portal(config: MystNodesPortalConfig, timeout_seconds: int) -> dict[str, Any]:
    email = os.getenv(config.email_env)
    password = os.getenv(config.password_env)
    if not email or not password:
        result = {
            "enabled": True,
            "authenticated": False,
            "error": f"missing {config.email_env} or {config.password_env}",
            "endpoints": {},
        }
        LOGGER.warning("MystNodes portal collection skipped result=%s", result)
        return result

    async with httpx.AsyncClient(base_url=config.base_url.rstrip("/"), timeout=timeout_seconds) as client:
        auth_data = await _login(client, config, email, password)
        token = auth_data.get("accessToken") or auth_data.get("access_token")
        portal: dict[str, Any] = {
            "enabled": True,
            "authenticated": bool(token),
            "base_url": config.base_url,
            "endpoints": {},
        }
        if not token:
            portal["error"] = "login response did not include access token"
            return portal

        headers = {"Authorization": f"Bearer {token}", "called-from": "mystmon-dev"}
        for endpoint in config.endpoints:
            portal["endpoints"][endpoint.name] = await _fetch_endpoint(client, endpoint, headers)
        nodes = _nodes_from_result(portal["endpoints"].get("nodes", {}))
        if nodes:
            LOGGER.info("MystNodes portal nodes summary count=%s", len(nodes))
            _log_node_summary(nodes)
            portal["node_details"] = await _collect_node_followups(client, config, headers, nodes)
        return portal


async def _login(
    client: httpx.AsyncClient,
    config: MystNodesPortalConfig,
    email: str,
    password: str,
) -> dict[str, Any]:
    path = "/api/v2/auth/login"
    payload = {"email": email, "password": password, "remember": config.remember}
    LOGGER.info(
        "MystNodes portal API call method=POST path=%s payload=%s",
        path,
        {"email": "<redacted>", "password": "<redacted>", "remember": config.remember},
    )
    try:
        response = await client.post(path, json=payload)
        data = _decode_response(response)
        result = {
            "ok": 200 <= response.status_code < 300,
            "status_code": response.status_code,
            "data": data,
        }
        LOGGER.info("MystNodes portal login status=%s ok=%s", response.status_code, result["ok"])
        response.raise_for_status()
        return data if isinstance(data, dict) else {}
    except httpx.HTTPError as exc:
        LOGGER.exception("MystNodes portal login failed error=%s", exc)
        return {}


async def _fetch_endpoint(
    client: httpx.AsyncClient,
    endpoint: MystNodesPortalEndpointConfig,
    headers: dict[str, str],
) -> dict[str, Any]:
    method = endpoint.method.upper()
    LOGGER.info(
        "MystNodes portal API call method=%s endpoint=%s path=%s params=%s",
        method,
        endpoint.name,
        endpoint.path,
        endpoint.params,
    )
    try:
        response = await client.request(method, endpoint.path, params=endpoint.params, headers=headers)
        data = _decode_response(response)
        result = {
            "ok": 200 <= response.status_code < 300,
            "status_code": response.status_code,
            "data": data,
        }
        _log_endpoint_result(endpoint.name, result)
        return result
    except httpx.HTTPError as exc:
        result = {"ok": False, "error": str(exc)}
        _log_endpoint_result(endpoint.name, result)
        return result


def _decode_response(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _safe_log_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": result.get("ok"),
        "status_code": result.get("status_code"),
        "error": result.get("error"),
        "data": _redact_api_value(result.get("data")),
    }


async def _collect_node_followups(
    client: httpx.AsyncClient,
    config: MystNodesPortalConfig,
    headers: dict[str, str],
    nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    details: dict[str, Any] = {"nodes": {}, "totals": None}
    identities = [str(node.get("identity")) for node in nodes if node.get("identity")]
    if config.node_totals_enabled and identities:
        params = {"days": config.node_totals_days, "identities": ",".join(identities)}
        details["totals"] = await _fetch_dynamic(client, "node_totals", "/api/v1/metrics/node-totals", headers, params)

    for node in nodes:
        node_id = str(node.get("id") or "")
        identity = str(node.get("identity") or "")
        node_key = identity or node_id
        if not node_key:
            continue
        node_result: dict[str, Any] = {}
        if config.node_detail_enabled:
            node_result["detail"] = await _fetch_dynamic(client, "node_detail", f"/api/v2/node/{node_key}", headers)
        if config.node_services_enabled:
            node_result["services"] = await _fetch_dynamic(client, "node_services", f"/api/v2/node/{node_key}/services", headers)
        details["nodes"][node_id] = node_result
    return details


async def _fetch_dynamic(
    client: httpx.AsyncClient,
    name: str,
    path: str,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    LOGGER.info("MystNodes portal API call method=GET endpoint=%s path=%s params=%s", name, path, params or {})
    try:
        response = await client.get(path, params=params or {}, headers=headers)
        data = _decode_response(response)
        result = {"ok": 200 <= response.status_code < 300, "status_code": response.status_code, "data": data}
        _log_endpoint_result(name, result)
        return result
    except httpx.HTTPError as exc:
        result = {"ok": False, "error": str(exc)}
        _log_endpoint_result(name, result)
        return result


def _nodes_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    data = result.get("data")
    if isinstance(data, dict) and isinstance(data.get("nodes"), list):
        return [node for node in data["nodes"] if isinstance(node, dict)]
    if isinstance(data, list):
        return [node for node in data if isinstance(node, dict)]
    return []


def _log_endpoint_result(endpoint: str, result: dict[str, Any]) -> None:
    status = result.get("status_code", "n/a")
    ok = result.get("ok")
    data = result.get("data")
    if endpoint == "me" and isinstance(data, dict):
        nodes_info = data.get("nodesInfo") or {}
        LOGGER.info(
            "MystNodes portal result endpoint=me status=%s ok=%s nodes_total=%s nodes_online=%s top_os=%s",
            status,
            ok,
            nodes_info.get("totalCount"),
            nodes_info.get("onlineCount"),
            nodes_info.get("topOS"),
        )
        return
    if endpoint == "nodes":
        nodes = _nodes_from_result(result)
        total = data.get("total") if isinstance(data, dict) else len(nodes)
        LOGGER.info("MystNodes portal result endpoint=nodes status=%s ok=%s total=%s returned=%s", status, ok, total, len(nodes))
        return
    if endpoint == "node_totals":
        LOGGER.info("MystNodes portal result endpoint=node_totals status=%s ok=%s summary=%s", status, ok, _compact_node_totals(data))
        return
    if endpoint in {"total_earnings", "total_transferred", "earnings_30d", "node_detail", "node_services"}:
        LOGGER.info("MystNodes portal result endpoint=%s status=%s ok=%s summary=%s", endpoint, status, ok, _compact_value(data))
        return
    LOGGER.info("MystNodes portal result endpoint=%s status=%s ok=%s", endpoint, status, ok)


def _log_node_summary(nodes: list[dict[str, Any]]) -> None:
    for node in nodes:
        status = node.get("nodeStatus") or {}
        earnings = node.get("earnings") or []
        earnings_total = _sum_earnings(earnings)
        LOGGER.info(
            "MystNodes node id=%s name=%s identity=%s online=%s quality=%s monitoring=%s version=%s local_ip=%s services=%s earnings_total=%.6f",
            node.get("id"),
            node.get("name"),
            node.get("identity"),
            status.get("online"),
            status.get("quality"),
            node.get("monitoringStatus"),
            node.get("version"),
            node.get("localIp"),
            ",".join(status.get("serviceTypes") or []),
            earnings_total,
        )


def _sum_earnings(earnings: Any) -> float:
    if not isinstance(earnings, list):
        return 0.0
    total = 0.0
    for item in earnings:
        if not isinstance(item, dict):
            continue
        try:
            total += float(item.get("etherAmount") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _compact_value(data: Any) -> str:
    if isinstance(data, dict):
        if "earningsTotal" in data:
            return f"earnings_total={data.get('earningsTotal')}"
        if "transferredTotal" in data:
            return f"transferred_total={data.get('transferredTotal')}"
        if "nodes" in data and isinstance(data["nodes"], list):
            return f"nodes={len(data['nodes'])} total={data.get('total')}"
        return urlencode({key: value for key, value in data.items() if not isinstance(value, (dict, list))})
    if isinstance(data, list):
        return f"items={len(data)} first={_redact_api_value(data[0]) if data else None}"
    if data is None:
        return "none"
    return str(_redact_api_value(data))


def _compact_node_totals(data: Any) -> str:
    if not isinstance(data, dict):
        return _compact_value(data)
    parts = []
    for key, value in data.items():
        if isinstance(value, dict):
            scalar_bits = [f"{inner_key}={inner_value}" for inner_key, inner_value in value.items() if not isinstance(inner_value, (dict, list))]
            parts.append(f"{key}({', '.join(scalar_bits[:6])})")
        elif isinstance(value, list):
            parts.append(f"{key}=items:{len(value)}")
        else:
            parts.append(f"{key}={value}")
    return "; ".join(parts[:12])
