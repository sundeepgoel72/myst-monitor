"""MystNodes portal collector for retrieving node information and account data.

This module provides functionality to collect data from the MystNodes portal
including account information, node details, and earnings data. It handles
authentication, API requests, and data parsing for MystNodes portal endpoints.

The collector supports multiple accounts and provides comprehensive data
about Mysterium nodes registered with MystNodes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from urllib.parse import urlencode
from typing import Any, Dict, List

import httpx

from mystmon.config import MystNodesPortalAccountConfig, MystNodesPortalEndpointConfig

LOGGER = logging.getLogger(__name__)


async def collect_mystnodes_portal_accounts(
    configs: List[MystNodesPortalAccountConfig],
    timeout_seconds: int,
    local_nodes: List[Dict[str, Any]] | None = None,
) -> List[Any]:
    """Collect data from multiple MystNodes portal accounts.
    
    Args:
        configs: List of portal account configurations
        timeout_seconds: Request timeout in seconds
        local_nodes: Optional list of local nodes for matching
        
    Returns:
        List of account data or error dictionaries
    """
    if not configs:
        return None

    # Filter to only enabled configs for actual collection
    enabled_configs = [config for config in configs if config.enabled]
    
    # Collect from all enabled accounts concurrently
    tasks = [
        collect_mystnodes_portal_account(config, timeout_seconds, local_nodes)
        for config in enabled_configs
    ]
    
    if not tasks:
        return None
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results - we only process results from enabled accounts
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            LOGGER.error("Portal collection failed for account %s: %s", 
                        enabled_configs[i].account if i < len(enabled_configs) else "unknown", 
                        str(result))
            # Return error dict instead of empty list to maintain consistent data structure
            processed_results.append({
                "enabled": True,
                "authenticated": False,
                "error": f"Collection failed: {str(result)}",
                "endpoints": {},
                "name": enabled_configs[i].account if i < len(enabled_configs) else "unknown",
            })
        elif result is None:
            # Return error dict for None results
            processed_results.append({
                "enabled": True,
                "authenticated": False,
                "error": "Collection returned None",
                "endpoints": {},
                "name": enabled_configs[i].account if i < len(enabled_configs) else "unknown",
            })
        else:
            processed_results.append(result)
    
    return processed_results


async def collect_mystnodes_portal(
    configs: List[MystNodesPortalAccountConfig],
    timeout_seconds: int,
    local_nodes: List[Dict[str, Any]] | None = None,
) -> List[Any] | None:
    """Backward-compatible alias for multi-account portal collection."""
    return await collect_mystnodes_portal_accounts(configs, timeout_seconds, local_nodes)


async def collect_mystnodes_portal_account(
    config: MystNodesPortalAccountConfig,
    timeout_seconds: int,
    local_nodes: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any] | None:
    """Collect data from a single MystNodes portal account.
    
    Args:
        config: Portal account configuration
        timeout_seconds: Request timeout in seconds
        local_nodes: Optional list of local nodes for matching
        
    Returns:
        Dictionary with account data or None if collection failed
    """
    email = config.account
    password = config.password or (os.getenv(config.password_env) if config.password_env else None)
    if not email or not password:
        result = {
            "enabled": True,
            "authenticated": False,
            "error": "missing account or password",
            "endpoints": {},
            "name": config.account,
        }
        LOGGER.warning(
            "MystNodes portal collection skipped for account %s reason=missing_credentials enabled=%s authenticated=%s",
            config.account,
            result["enabled"],
            result["authenticated"],
        )
        return result

    base_url = str(config.base_url or "").rstrip("/")
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds) as client:
        auth_data = await _login(client, config, email, password)
        token = auth_data.get("accessToken") or auth_data.get("access_token")
        portal: Dict[str, Any] = {
            "enabled": True,
            "authenticated": bool(token),
            "base_url": config.base_url,
            "wallet_address_hint": _wallet_address_hint(config.wallet_address),
            "endpoints": {},
            "name": config.account,
        }
        if not token:
            portal["error"] = "login response did not include access token"
            LOGGER.error(
                "MystNodes portal collection failed for account %s reason=missing_access_token base_url=%s wallet=%s",
                config.account,
                config.base_url,
                portal["wallet_address_hint"],
            )
            return portal

        headers = {"Authorization": f"Bearer {token}", "called-from": "mystmon-dev"}
        for endpoint in config.endpoints:
            await _throttle(config)
            portal["endpoints"][endpoint.name] = await _fetch_endpoint(client, config, endpoint, headers)
        nodes = _nodes_from_result(portal["endpoints"].get("nodes", {}))
        if nodes:
            portal["nodes"] = nodes
            LOGGER.info("MystNodes portal nodes summary for account %s count=%s", config.account, len(nodes))
            _log_node_summary(nodes)
            portal["local_matches"] = _match_local_nodes(nodes, local_nodes or [])
            _log_local_matches(nodes, portal["local_matches"])
            portal["node_details"] = await _collect_node_followups(client, config, headers, nodes)
        return portal


async def _login(
    client: httpx.AsyncClient,
    config: MystNodesPortalAccountConfig,
    email: str,
    password: str,
) -> Dict[str, Any]:
    """Login to the MystNodes portal.
    
    Args:
        client: HTTP client
        config: Portal account configuration
        email: User email
        password: User password
        
    Returns:
        Dictionary with authentication data
    """
    path = "/api/v2/auth/login"
    payload = {"email": email, "password": password, "remember": config.remember}
    LOGGER.info(
        "MystNodes portal API call method=POST path=%s payload=%s",
        path,
        {"email": "<redacted>", "password": "<redacted>", "remember": config.remember},
    )
    try:
        result = await _request_json(client, config, "POST", path, json=payload)
        data = result.get("data")
        status_code = result.get("status_code")
        result = {
            "ok": result.get("ok"),
            "status_code": status_code,
            "data": data,
        }
        LOGGER.info("MystNodes portal login status=%s ok=%s", status_code, result["ok"])
        return data if result["ok"] and isinstance(data, dict) else {}
    except httpx.HTTPError as exc:
        LOGGER.exception(
            "MystNodes portal login failed reason=http_error base_url=%s error=%s",
            config.base_url,
            exc,
        )
        return {}


async def _fetch_endpoint(
    client: httpx.AsyncClient,
    config: MystNodesPortalAccountConfig,
    endpoint: MystNodesPortalEndpointConfig,
    headers: Dict[str, str],
) -> Dict[str, Any]:
    """Fetch data from a portal endpoint.
    
    Args:
        client: HTTP client
        config: Portal account configuration
        endpoint: Endpoint configuration
        headers: Request headers
        
    Returns:
        Dictionary with endpoint data
    """
    method = endpoint.method.upper()
    params = dict(endpoint.params)
    if endpoint.name == "wallet_balance" and config.wallet_address:
        params.setdefault("walletAddress", config.wallet_address)
        params.setdefault("address", config.wallet_address)
    LOGGER.info(
        "MystNodes portal API call method=%s endpoint=%s path=%s params=%s",
        method,
        endpoint.name,
        endpoint.path,
        _redact_portal_params(params),
    )
    try:
        result = await _request_json(client, config, method, endpoint.path, params=params, headers=headers)
        _log_endpoint_result(endpoint.name, result)
        return result
    except httpx.HTTPError as exc:
        result = {"ok": False, "error": str(exc)}
        LOGGER.error(
            "MystNodes portal endpoint failed endpoint=%s path=%s reason=http_error error=%s",
            endpoint.name,
            endpoint.path,
            exc,
        )
        _log_endpoint_result(endpoint.name, result)
        return result


def _decode_response(response: httpx.Response) -> Any:
    """Decode HTTP response.
    
    Args:
        response: HTTP response
        
    Returns:
        Decoded response data
    """
    try:
        return response.json()
    except ValueError:
        return response.text


def _safe_log_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Safely log result data by redacting sensitive information.
    
    Args:
        result: Result data to log
        
    Returns:
        Redacted result data
    """
    return {
        "ok": result.get("ok"),
        "status_code": result.get("status_code"),
        "error": result.get("error"),
        "data": _redact_api_value(result.get("data")),
    }


async def _collect_node_followups(
    client: httpx.AsyncClient,
    config: MystNodesPortalAccountConfig,
    headers: Dict[str, str],
    nodes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Collect additional data for nodes.
    
    Args:
        client: HTTP client
        config: Portal account configuration
        headers: Request headers
        nodes: List of nodes
        
    Returns:
        Dictionary with node details
    """
    details: Dict[str, Any] = {"nodes": {}, "totals": None}
    identities = [str(node.get("identity")) for node in nodes if node.get("identity")]
    if config.node_totals_enabled and identities:
        params = {"days": config.node_totals_days, "identities": ",".join(identities)}
        await _throttle(config)
        details["totals"] = await _fetch_dynamic(client, config, "node_totals", "/api/v1/metrics/node-totals", headers, params)

    for node in nodes:
        node_id = str(node.get("id") or "")
        identity = str(node.get("identity") or "")
        node_key = identity or node_id
        if not node_key:
            continue
        node_result: Dict[str, Any] = {}
        if config.node_detail_enabled:
            await _throttle(config)
            node_result["detail"] = await _fetch_dynamic(client, config, "node_detail", f"/api/v2/node/{node_key}", headers)
        if config.node_services_enabled:
            await _throttle(config)
            node_result["services"] = await _fetch_dynamic(client, config, "node_services", f"/api/v2/node/{node_key}/services", headers)
        details["nodes"][node_id] = node_result
    return details


async def _throttle(config: MystNodesPortalAccountConfig) -> None:
    """Throttle requests if configured.
    
    Args:
        config: Portal account configuration
    """
    if config.request_delay_seconds > 0:
        await asyncio.sleep(config.request_delay_seconds)


async def _fetch_dynamic(
    client: httpx.AsyncClient,
    config: MystNodesPortalAccountConfig,
    name: str,
    path: str,
    headers: Dict[str, str],
    params: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Fetch data from a dynamic endpoint.
    
    Args:
        client: HTTP client
        config: Portal account configuration
        name: Endpoint name
        path: Endpoint path
        headers: Request headers
        params: Request parameters
        
    Returns:
        Dictionary with endpoint data
    """
    LOGGER.info(
        "MystNodes portal API call method=GET endpoint=%s path=%s params=%s",
        name,
        path,
        _redact_portal_params(_compact_params(name, params or {})),
    )
    try:
        result = await _request_json(client, config, "GET", path, params=params or {}, headers=headers)
        _log_endpoint_result(name, result)
        return result
    except httpx.HTTPError as exc:
        result = {"ok": False, "error": str(exc)}
        LOGGER.error(
            "MystNodes portal endpoint failed endpoint=%s path=%s reason=http_error error=%s",
            name,
            path,
            exc,
        )
        _log_endpoint_result(name, result)
        return result


async def _request_json(
    client: httpx.AsyncClient,
    config: MystNodesPortalAccountConfig | None,
    method: str,
    path: str,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Make an HTTP request with retry logic.
    
    Args:
        client: HTTP client
        config: Portal account configuration
        method: HTTP method
        path: Request path
        **kwargs: Additional request arguments
        
    Returns:
        Dictionary with response data
    """
    retry_count = config.retry_count if config else 0
    retry_delay = config.retry_delay_seconds if config else 0
    attempts = retry_count + 1
    last_result: Dict[str, Any] = {"ok": False, "error": "request not attempted"}
    for attempt in range(1, attempts + 1):
        try:
            response = await client.request(method, path, **kwargs)
            data = _decode_response(response)
            last_result = {"ok": 200 <= response.status_code < 300, "status_code": response.status_code, "data": data, "attempt": attempt}
            if last_result["ok"] or not _should_retry_status(response.status_code) or attempt == attempts:
                return last_result
            LOGGER.info(
                "MystNodes portal retrying method=%s path=%s status=%s attempt=%s/%s delay_seconds=%s",
                method,
                path,
                response.status_code,
                attempt,
                attempts,
                retry_delay,
            )
        except httpx.HTTPError as exc:
            _log_dns_failure_if_applicable(client, method, path, exc)
            last_result = {"ok": False, "error": str(exc), "attempt": attempt}
            if attempt == attempts:
                LOGGER.error(
                    "MystNodes portal request failed method=%s path=%s reason=http_error attempts=%s error=%s",
                    method,
                    path,
                    attempts,
                    exc,
                )
                return last_result
            LOGGER.info(
                "MystNodes portal retrying method=%s path=%s error=%s attempt=%s/%s delay_seconds=%s",
                method,
                path,
                exc,
                attempt,
                attempts,
                retry_delay,
            )
        if retry_delay > 0:
            await asyncio.sleep(retry_delay)
    LOGGER.error(
        "MystNodes portal request failed method=%s path=%s reason=retry_exhausted attempts=%s",
        method,
        path,
        attempts,
    )
    return last_result


def _log_dns_failure_if_applicable(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    exc: httpx.HTTPError,
) -> None:
    """Log DNS resolution failures explicitly.
    
    Args:
        client: HTTP client
        method: HTTP method
        path: Request path
        exc: Exception
    """
    message = str(exc)
    if "gaierror" not in message and "Name or service not known" not in message and "Temporary failure in name resolution" not in message:
        return
    base_url = getattr(client, "base_url", None)
    host = getattr(base_url, "host", None)
    LOGGER.error(
        "MystNodes portal DNS resolution failed method=%s path=%s host=%s error=%s",
        method,
        path,
        host,
        exc,
    )


def _should_retry_status(status_code: int) -> bool:
    """Determine if a status code should be retried.
    
    Args:
        status_code: HTTP status code
        
    Returns:
        True if status code should be retried
    """
    return status_code in {408, 429, 500, 502, 503, 504}


def _nodes_from_result(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract nodes from API result.
    
    Args:
        result: API result
        
    Returns:
        List of nodes
    """
    data = result.get("data")
    if isinstance(data, dict) and isinstance(data.get("nodes"), list):
        return [node for node in data["nodes"] if isinstance(node, dict)]
    if isinstance(data, list):
        return [node for node in data if isinstance(node, dict)]
    return []


def _match_local_nodes(portal_nodes: List[Dict[str, Any]], local_nodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Match portal nodes with local Docker containers.
    
    Args:
        portal_nodes: List of portal nodes
        local_nodes: List of local nodes
        
    Returns:
        Dictionary mapping node IDs to local node data
    """
    by_ip: Dict[str, Dict[str, Any]] = {}
    for local_node in local_nodes:
        for network in local_node.get("networks", []):
            ip_address = network.get("ip_address")
            if ip_address:
                by_ip[str(ip_address)] = local_node
            if network.get("name") == "host" and local_node.get("host"):
                by_ip[str(local_node["host"])] = local_node

    matches: Dict[str, Dict[str, Any]] = {}
    for portal_node in portal_nodes:
        node_id = str(portal_node.get("id") or "")
        local_ip = str(portal_node.get("localIp") or "")
        local_node = by_ip.get(local_ip)
        if not node_id or not local_node:
            continue
        matches[node_id] = _local_node_summary(local_node)
    return matches


def _local_node_summary(local_node: Dict[str, Any]) -> Dict[str, Any]:
    """Create a summary of a local node.
    
    Args:
        local_node: Local node data
        
    Returns:
        Summary of local node
    """
    return {
        "name": local_node.get("name"),
        "container_name": local_node.get("container_name"),
        "host": local_node.get("host"),
        "running": local_node.get("running"),
        "status": local_node.get("status"),
        "restart_count": local_node.get("restart_count"),
        "uptime_seconds": local_node.get("uptime_seconds"),
        "networks": local_node.get("networks", []),
        "log_counts": local_node.get("log_counts", {}),
        "warnings": local_node.get("warnings", []),
    }


def _log_local_matches(portal_nodes: List[Dict[str, Any]], matches: Dict[str, Dict[str, Any]]) -> None:
    """Log information about local node matches.
    
    Args:
        portal_nodes: List of portal nodes
        matches: Dictionary of node matches
    """
    for portal_node in portal_nodes:
        node_id = str(portal_node.get("id") or "")
        local_ip = portal_node.get("localIp")
        match = matches.get(node_id)
        if not match:
            LOGGER.info("MystNodes local match node_id=%s name=%s local_ip=%s matched=False", node_id, portal_node.get("name"), local_ip)
            continue
        LOGGER.info(
            "MystNodes local match node_id=%s name=%s local_ip=%s matched=True container=%s host=%s running=%s restarts=%s uptime_seconds=%s log_errors=%s warnings=%s",
            node_id,
            portal_node.get("name"),
            local_ip,
            match.get("container_name") or match.get("name"),
            match.get("host"),
            match.get("running"),
            match.get("restart_count"),
            match.get("uptime_seconds"),
            match.get("log_counts", {}).get("error_or_warning"),
            ",".join(match.get("warnings") or []),
        )


def _log_endpoint_result(endpoint: str, result: Dict[str, Any]) -> None:
    """Log endpoint result information.
    
    Args:
        endpoint: Endpoint name
        result: Result data
    """
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


def _log_node_summary(nodes: List[Dict[str, Any]]) -> None:
    """Log summary information about nodes.
    
    Args:
        nodes: List of nodes
    """
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
    """Sum earnings from various formats.
    
    Args:
        earnings: Earnings data
        
    Returns:
        Total earnings as float
    """
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
    """Create a compact string representation of data.
    
    Args:
        data: Data to compact
        
    Returns:
        Compact string representation
    """
    if isinstance(data, dict):
        if "nodeStatus" in data or "monitoringStatus" in data:
            status = data.get("nodeStatus") or {}
            return (
                f"id={data.get('id')} name={data.get('name')} online={status.get('online')} "
                f"quality={status.get('quality')} monitoring={data.get('monitoringStatus')} "
                f"version={data.get('version')} local_ip={data.get('localIp')} "
                f"uptime_min_24h={data.get('uptimeMinLast24H')}"
            )
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


def _compact_params(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Compact parameters for logging.
    
    Args:
        endpoint: Endpoint name
        params: Parameters to compact
        
    Returns:
        Compacted parameters
    """
    if endpoint == "node_totals" and "identities" in params:
        identities = str(params.get("identities") or "")
        identity_count = len([item for item in identities.split(",") if item])
        return {"days": params.get("days"), "identity_count": identity_count}
    return params


def _redact_portal_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Redact sensitive parameters.
    
    Args:
        params: Parameters to redact
        
    Returns:
        Redacted parameters
    """
    redacted = dict(params)
    for key in {"walletAddress", "address"}:
        if key in redacted and redacted[key]:
            redacted[key] = _wallet_address_hint(str(redacted[key]))
    return redacted


def _wallet_address_hint(wallet_address: str | None) -> str | None:
    """Create a hint from a wallet address.
    
    Args:
        wallet_address: Wallet address
        
    Returns:
        Wallet address hint or None
    """
    if not wallet_address:
        return None
    wallet = str(wallet_address).strip()
    if len(wallet) <= 10:
        return "<redacted>"
    return f"{wallet[:6]}…{wallet[-4:]}"


def _compact_node_totals(data: Any) -> str:
    """Create a compact representation of node totals.
    
    Args:
        data: Node totals data
        
    Returns:
        Compact representation of node totals
    """
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


def _redact_api_value(value: Any, max_chars: int = 2000) -> Any:
    """Redact sensitive information from API values."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_name = str(key)
            if not _is_log_safe_key(key_name):
                redacted[key_name] = "***REDACTED***"
            else:
                redacted[key_name] = _redact_api_value(item, max_chars)
        return redacted
    if isinstance(value, list):
        return [_redact_api_value(item, max_chars) for item in value[:20]]
    if isinstance(value, str):
        if re.search(r"\b0x[a-fA-F0-9]{40}\b", value):
            return False
        sensitive_patterns = [
            r"(?<!0x)[a-zA-Z0-9]{32,}",
            r"password|secret|token|private|key|mnemonic|wallet|hash",
        ]
        lower_value = value.lower()
        for pattern in sensitive_patterns:
            if re.search(pattern, lower_value):
                return "***REDACTED***"
        return value if len(value) <= max_chars else f"{value[:max_chars]}...<truncated>"
    return value


def _is_log_safe_key(key: str) -> bool:
    """Check if a key is safe to log."""
    lowered = key.lower()
    blocked = ("password", "secret", "token", "private", "key", "mnemonic", "email", "wallet", "hash", "address")
    return not any(item in lowered for item in blocked)
