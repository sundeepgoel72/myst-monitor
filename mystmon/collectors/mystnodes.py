from __future__ import annotations

import logging
import os
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
        return portal


async def _login(
    client: httpx.AsyncClient,
    config: MystNodesPortalConfig,
    email: str,
    password: str,
) -> dict[str, Any]:
    path = "/api/v2/auth/login"
    payload = {"email": email, "password": password, "remember": config.remember}
    LOGGER.info("MystNodes portal API call method=POST path=%s payload=%s", path, {"email": email, "password": "<redacted>", "remember": config.remember})
    try:
        response = await client.post(path, json=payload)
        data = _decode_response(response)
        result = {
            "ok": 200 <= response.status_code < 300,
            "status_code": response.status_code,
            "data": data,
        }
        LOGGER.info("MystNodes portal API result endpoint=login result=%s", _safe_log_result(result))
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
        LOGGER.info("MystNodes portal API result endpoint=%s result=%s", endpoint.name, _safe_log_result(result))
        return result
    except httpx.HTTPError as exc:
        result = {"ok": False, "error": str(exc)}
        LOGGER.info("MystNodes portal API result endpoint=%s result=%s", endpoint.name, _safe_log_result(result))
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
