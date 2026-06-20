"""Mysterium node collector for retrieving metrics from TequilAPI endpoints."""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from datetime import datetime
from typing import Any, Dict, List

import httpx

from mystmon.config import (
    MystCollectorConfig,
    MystRemoteHostConfig,
    TequilApiEndpointConfig,
)
from mystmon.storage import Reading

LOGGER = logging.getLogger(__name__)

# TequilAPI endpoints that should not be called automatically
BLOCKED_ENDPOINTS = {
    "/stop",
    "/auth/login",
    "/auth/logout",
    "/identities/{id}/register",
    "/identities/{id}/topup",
    "/feedback",
    "/connection",
    "/connection/{id}",
    "/connection/manual",
    "/connection/shutdown",
    "/connection/location",
    "/config/user",
    "/config/set",
    "/identities/create",
    "/identities/import",
    "/identities/register",
    "/services",
    "/services/{id}",
    "/transactor/settle",
    "/transactor/settle/{id}",
    "/transactor/staking",
    "/transactor/rewards",
    "/transactor/payments",
    "/pilvytis/api/v1/order",
    "/pilvytis/api/v1/payment",
}

# These endpoints are configured in older repo defaults but are not usable on
# the currently observed node versions. Skip them to avoid noisy collection
# errors until a version-specific implementation is added.
SKIPPED_ENDPOINTS = {
    "/node/provider/sessions",
    "/node/provider/transferred-data",
    "/settle/history",
    "/transactor/chains-summary",
}

# Endpoints that are safe to call for metrics collection
SAFE_ENDPOINTS = {
    "/healthcheck",
    "/identities",
    "/services",
    "/sessions",
    "/sessions-connectivity-status",
    "/sessions/stats-daily",
    "/sessions/stats-aggregated",
    "/node/provider/activity-stats",
    "/node/provider/quality",
    "/node/provider/service-earnings",
    "/node/provider/sessions",
    "/node/provider/sessions-count",
    "/node/provider/transferred-data",
    "/settle/history",
    "/transactor/chains-summary",
    "/transactor/fees",
    "/v2/transactor/fees",
    "/config",
    "/config/default",
    "/connection/location",
    "/connection/proxy/location",
    "/location",
    "/nat/type",
}

# Backward-compatible alias retained for older tests and call sites.
BLOCKED_PATHS = BLOCKED_ENDPOINTS | {
    "/identities/{id}/unlock",
    "/settle/withdraw",
    "/settle/pay",
    "/bug-report",
}

# Default metrics to collect if no endpoints are configured
DEFAULT_ENDPOINTS = [
    {"name": "healthcheck", "path": "/healthcheck", "metric_prefix": "health"},
    {"name": "identities", "path": "/identities", "metric_prefix": "identities"},
    {"name": "services", "path": "/services", "metric_prefix": "services"},
    {"name": "sessions", "path": "/sessions", "metric_prefix": "sessions"},
    {"name": "provider_quality", "path": "/node/provider/quality", "metric_prefix": "provider"},
    {"name": "provider_earnings", "path": "/node/provider/service-earnings", "metric_prefix": "provider"},
    {"name": "payments", "path": "/v2/transactor/fees", "metric_prefix": "payments"},
    {"name": "location", "path": "/location", "metric_prefix": "location"},
    {"name": "nat_type", "path": "/nat/type", "metric_prefix": "nat"},
]


def _is_connectivity_error(exc: BaseException) -> bool:
    return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError))


def _api_auth(config: MystCollectorConfig) -> tuple[str, str] | None:
    import os

    if not config.api_username or not config.api_password_env:
        return None
    password = os.getenv(config.api_password_env)
    if not password:
        return None
    return (config.api_username, password)


def _contains_sensitive_data(value: str) -> bool:
    lower_value = value.lower()
    if "0x" in lower_value and re.search(r"0x[a-f0-9]{40}", lower_value):
        # Public wallet addresses are not sensitive by themselves.
        if re.fullmatch(r".*0x[a-f0-9]{40}.*", lower_value) and "address:" in lower_value:
            return False
    sensitive_keywords = (
        "password",
        "secret",
        "token",
        "private",
        "key",
        "mnemonic",
        "wallet",
        "hash",
        "private_key",
        "secret_token",
    )
    if any(keyword in lower_value for keyword in sensitive_keywords):
        return True
    return bool(re.search(r"[a-z0-9]{32,}", lower_value))


def _redact_api_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, nested_value in value.items():
            if _contains_sensitive_data(str(key)):
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = _redact_api_value(nested_value)
        return redacted
    if isinstance(value, list):
        return [_redact_api_value(item) for item in value]
    if isinstance(value, str) and _contains_sensitive_data(value):
        return "***REDACTED***"
    return value


def _node_display_name(container_name: str, api_probe: dict[str, Any] | None) -> str:
    if api_probe:
        identity = api_probe.get("identity")
        if identity:
            return str(identity)
        labels = api_probe.get("labels") or {}
        if labels.get("identity_id"):
            return str(labels["identity_id"])
    return container_name


def extract_api_metrics(endpoint_name: str, category: str, data: Any) -> dict[str, Any]:
    metrics: dict[str, float] = {}
    labels: dict[str, str] = {}

    if category == "health" and isinstance(data, dict):
        uptime = data.get("uptime")
        if isinstance(uptime, str):
            metrics["health_uptime_seconds"] = float(_parse_duration_to_seconds(uptime))
        version = data.get("version")
        if version is not None:
            labels["health_version"] = str(version)
        build_info = data.get("build_info")
        if isinstance(build_info, dict):
            if build_info.get("commit") is not None:
                labels["health_build_commit"] = str(build_info["commit"])
    elif category == "identities" and isinstance(data, dict):
        identities = data.get("identities")
        if isinstance(identities, list):
            metrics["identities_count"] = float(len(identities))
    elif category == "services" and isinstance(data, dict):
        services = data.get("services")
        if isinstance(services, list):
            metrics["services_count"] = float(len(services))
            metrics["services_running_count"] = float(sum(1 for item in services if isinstance(item, dict) and item.get("running")))
    elif category == "sessions" and isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                metrics[f"sessions_{key}"] = float(value)
    elif category == "provider" and isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                metrics[f"provider_{key}"] = float(value)
    elif category == "payments" and isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                metrics[f"payments_{key}"] = float(value)
    elif category == "location" and isinstance(data, dict):
        for key, value in data.items():
            labels[f"location_{key}"] = str(value)
    elif category == "nat":
        labels["nat"] = str(data)
    else:
        metrics.update(_extract_metrics_from_response(data, category))

    return {"metrics": metrics, "labels": labels}


def _parse_duration_to_seconds(value: str) -> int:
    total = 0
    for amount, unit in re.findall(r"(\d+)([hms])", value):
        if unit == "h":
            total += int(amount) * 3600
        elif unit == "m":
            total += int(amount) * 60
        else:
            total += int(amount)
    return total


def summarize_logs(log_text: str) -> dict[str, int]:
    lower_text = log_text.lower()
    lines = [line for line in lower_text.splitlines() if line.strip()]
    return {
        "error_or_warning": sum(1 for line in lines if "[error]" in line or "[warn]" in line),
        "promise": sum(1 for line in lines if "promise" in line),
        "session": sum(1 for line in lines if "session" in line),
        "identity_warning": sum(1 for line in lines if "password or unlock" in line),
    }


async def collect_myst(
    config: MystCollectorConfig,
    timeout_seconds: int,
    portal_nodes: List[Dict[str, Any]] | None = None,
) -> List[Reading]:
    """Collect metrics from Mysterium nodes."""
    readings: List[Reading] = []

    # Portal-derived local runtime discovery is the preferred runtime path.
    local_readings = await _collect_portal_runtime_nodes(config, timeout_seconds, portal_nodes or [])
    readings.extend(local_readings)

    # Static target lists are legacy fallback/debug inputs only.
    if config.fallback_targets_enabled and not local_readings and not portal_nodes:
        readings.extend(await _collect_configured_containers(config, timeout_seconds))

    if config.fallback_targets_enabled:
        remote_readings = await _collect_remote_hosts(config, timeout_seconds)
        readings.extend(remote_readings)
    return readings


def render_myst_snapshot(snapshot: dict[str, Any]) -> str:
    """Render myst snapshot data to string format.
    
    Args:
        snapshot: Snapshot data dictionary
        
    Returns:
        Formatted string representation of the snapshot
    """
    lines = []
    
    # Add header
    lines.append("# Mysterium Node Snapshot")
    lines.append("")
    
    # Add container information
    if "containers" in snapshot:
        lines.append("## Containers")
        for container in snapshot.get("containers", []):
            lines.append(f"- **{container.get('name', 'Unknown')}**")
            lines.append(f"  - Status: {container.get('status', 'unknown')}")
            lines.append(f"  - Running: {container.get('running', False)}")
            if container.get("uptime_seconds") is not None:
                lines.append(f"  - Uptime: {container.get('uptime_seconds', 0):.0f}s")
            lines.append("")
    
    # Add API information
    if "api_endpoints" in snapshot:
        lines.append("## API Endpoints")
        for endpoint in snapshot.get("api_endpoints", []):
            lines.append(f"- **{endpoint.get('name', 'Unknown')}** ({endpoint.get('path', '/')})")
            lines.append(f"  - Status: {endpoint.get('status', 'unknown')}")
            if "response_time" in endpoint:
                lines.append(f"  - Response Time: {endpoint.get('response_time', 0):.2f}ms")
            lines.append("")
    
    # Add metrics
    if "metrics" in snapshot:
        lines.append("## Metrics")
        for metric in snapshot.get("metrics", []):
            lines.append(f"- {metric.get('name', 'unknown')}: {metric.get('value', 0)}")
        lines.append("")
    
    return "\n".join(lines)


async def _collect_portal_runtime_nodes(
    config: MystCollectorConfig,
    timeout_seconds: int,
    portal_nodes: List[Dict[str, Any]],
) -> List[Reading]:
    host_infos: list[dict[str, Any]] = []
    seen_hosts: set[str] = set()
    for portal_node in portal_nodes:
        if not isinstance(portal_node, dict):
            continue
        host = str(portal_node.get("localIp") or "").strip()
        identity = str(portal_node.get("identity") or "").strip()
        if not host or host in seen_hosts:
            continue
        seen_hosts.add(host)
        node_name = str(portal_node.get("name") or identity or host)
        host_infos.append({
            "name": node_name,
            "container_name": node_name,
            "host": host,
            "running": None,
            "status": "unknown",
            "restart_count": 0,
            "uptime_seconds": None,
            "networks": [{"name": "host", "ip_address": host, "gateway": None}],
            "log_counts": {},
            "portal_identity": identity,
            "portal_node_name": node_name,
            "warnings": [],
        })

    if not host_infos:
        return []

    async def _probe_host(host_info: dict[str, Any]) -> list[Reading]:
        base_url = f"http://{host_info['host']}:{config.api_default_port}"
        try:
            return await asyncio.wait_for(
                _probe_api(base_url, config, timeout_seconds, host_info),
                timeout=max(3, timeout_seconds + 2),
            )
        except asyncio.TimeoutError:
            LOGGER.warning("Portal-derived runtime probe timed out host=%s", host_info["host"])
            host_info["running"] = False
            host_info["status"] = "timeout"
            return [
                Reading(
                    source_type="myst",
                    source_name=host_info["name"],
                    metric_name="api_up",
                    value=0.0,
                    labels={},
                    timestamp=datetime.now(),
                    raw_data=host_info,
                )
            ]

    results = await asyncio.gather(*[_probe_host(host_info) for host_info in host_infos], return_exceptions=True)
    readings: list[Reading] = []
    for host_info, result in zip(host_infos, results):
        if isinstance(result, Exception):
            LOGGER.warning("Portal-derived runtime probe failed host=%s error=%s", host_info["host"], result)
            host_info["running"] = False
            host_info["status"] = "error"
            readings.append(
                Reading(
                    source_type="myst",
                    source_name=host_info["name"],
                    metric_name="api_up",
                    value=0.0,
                    labels={},
                    timestamp=datetime.now(),
                    raw_data=host_info,
                )
            )
            continue
        readings.extend(result)
    return readings


async def _collect_configured_containers(config: MystCollectorConfig, timeout_seconds: int) -> List[Reading]:
    """Collect metrics from configured containers.
    
    Args:
        config: Collector configuration
        timeout_seconds: Request timeout in seconds
        
    Returns:
        List of readings from configured containers
    """
    readings: List[Reading] = []
    for container_config in config.containers:
        try:
            container_readings = await _collect_configured_container(container_config, config, timeout_seconds)
            readings.extend(container_readings)
        except Exception:
            LOGGER.exception("Configured container collection failed name=%s", container_config.name)
    
    return readings


async def _collect_remote_hosts(config: MystCollectorConfig, timeout_seconds: int) -> List[Reading]:
    """Collect metrics from remote hosts derived from portal information.
    
    Args:
        config: Collector configuration
        timeout_seconds: Request timeout in seconds
        
    Returns:
        List of readings from remote hosts
    """
    readings: List[Reading] = []
    for host_config in config.remote_hosts:
        if not host_config.enabled:
            continue
            
        try:
            host_readings = await _collect_remote_host(host_config, config, timeout_seconds)
            readings.extend(host_readings)
        except Exception:
            LOGGER.exception("Remote host collection failed host=%s", host_config.host)
    
    return readings


async def _collect_configured_container(
    container_config,
    collector_config: MystCollectorConfig,
    timeout_seconds: int,
) -> List[Reading]:
    """Collect metrics from a configured container.
    
    Args:
        container_config: Container configuration
        collector_config: Collector configuration
        timeout_seconds: Request timeout in seconds
        
    Returns:
        List of readings from the container
    """
    name = container_config.name
    host = container_config.host
    port = container_config.tequilapi_port or collector_config.api_default_port
    base_url = f"http://{host}:{port}"
    
    # Create basic container info
    container_info = {
        "name": name,
        "container_name": name,
        "host": host,
        "running": None,
        "status": "unknown",
        "restart_count": 0,
        "uptime_seconds": None,
        "networks": [{"name": "host", "ip_address": host, "gateway": None}],
        "log_counts": {},
        "warnings": ["configured_runtime_fallback"],
    }
    
    # Probe TequilAPI
    api_readings = await _probe_api(base_url, collector_config, timeout_seconds, container_info)
    return api_readings


async def _collect_remote_host(
    host_config: MystRemoteHostConfig,
    collector_config: MystCollectorConfig,
    timeout_seconds: int,
) -> List[Reading]:
    """Collect metrics from a single remote host.
    
    Args:
        host_config: Remote host configuration
        collector_config: Collector configuration
        timeout_seconds: Request timeout in seconds
        
    Returns:
        List of readings from the remote host
    """
    host = host_config.host
    port = host_config.tequilapi_port or collector_config.api_default_port
    base_url = f"http://{host}:{port}"
    
    # Create basic host info
    host_info = {
        "name": f"remote-{host}",
        "host": host,
        "container_name": None,
        "running": True,
        "status": "running",
        "restart_count": 0,
        "uptime_seconds": None,
        "networks": [],
        "log_counts": {},
    }
    
    # Probe TequilAPI
    api_readings = await _probe_api(base_url, collector_config, timeout_seconds, host_info)
    return api_readings


async def _probe_api(
    base_url: str,
    config: MystCollectorConfig,
    timeout_seconds: int,
    container_info: Dict[str, Any],
) -> List[Reading]:
    """Probe TequilAPI endpoints.
    
    Args:
        base_url: Base URL for the API
        config: Collector configuration
        timeout_seconds: Request timeout in seconds
        container_info: Container information
        
    Returns:
        List of API readings
    """
    name = container_info["name"]
    timestamp = datetime.now()
    readings: List[Reading] = []

    # Check if API is accessible
    request_timeout = httpx.Timeout(timeout_seconds, connect=min(3.0, float(timeout_seconds)))
    health_error: Exception | None = None
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=request_timeout) as client:
            response = await client.get("/healthcheck")
            api_up = response.status_code == 200
            health_data = _decode_api_response(response) if api_up else None
    except Exception as exc:
        api_up = False
        health_data = None
        health_error = exc

    container_info["running"] = api_up
    container_info["status"] = "running" if api_up else "unreachable"
    api = {
        "up": api_up,
        "metrics": {},
        "endpoints": {
            "healthcheck": {
                "ok": api_up,
                "status_code": 200 if api_up else None,
                "path": "/healthcheck",
                "data": health_data,
                "error": str(health_error) if health_error else None,
            }
        },
        "status_code": 200 if api_up else None,
    }
    if container_info.get("portal_identity"):
        api["identity"] = container_info["portal_identity"]
    container_info["api"] = api
    
    readings.append(Reading(
        source_type="myst",
        source_name=name,
        metric_name="api_up",
        value=1.0 if api_up else 0.0,
        labels={},
        timestamp=timestamp,
        raw_data=container_info,
    ))
    
    if not api_up:
        return readings
    
    endpoints = [
        endpoint_config
        for endpoint_config in (config.api_endpoints or _create_default_endpoints())
        if endpoint_config.path not in BLOCKED_ENDPOINTS
        and endpoint_config.path not in SKIPPED_ENDPOINTS
        and endpoint_config.path != "/healthcheck"
    ]
    results = await asyncio.gather(
        *[
            _fetch_api_endpoint(
                base_url,
                config,
                timeout_seconds,
                endpoint_config,
                name,
                timestamp,
                container_info,
            )
            for endpoint_config in endpoints
        ],
        return_exceptions=True,
    )
    for endpoint_config, result in zip(endpoints, results):
        if isinstance(result, Exception):
            LOGGER.warning(
                "API endpoint collection failed name=%s endpoint=%s path=%s error=%s",
                name,
                endpoint_config.name,
                endpoint_config.path,
                result,
            )
            continue
        readings.extend(result)

    return readings


def _create_default_endpoints():
    """Create default endpoint configurations."""
    return [TequilApiEndpointConfig(**endpoint) for endpoint in DEFAULT_ENDPOINTS]


async def _fetch_api_endpoint(
    base_url: str,
    config: MystCollectorConfig,
    timeout_seconds: int,
    endpoint_config,
    source_name: str,
    timestamp: datetime,
    container_info: Dict[str, Any],
) -> List[Reading]:
    """Fetch data from a single API endpoint.
    
    Args:
        base_url: Base URL for the API
        config: Collector configuration
        timeout_seconds: Request timeout in seconds
        endpoint_config: Endpoint configuration
        source_name: Source name for readings
        timestamp: Timestamp for readings
        container_info: Container information
        
    Returns:
        List of readings from the endpoint
    """
    path = endpoint_config.path
    readings: List[Reading] = []
    
    try:
        headers = {}
        if config.api_username and config.api_password_env:
            import os
            password = os.getenv(config.api_password_env)
            if password:
                auth_string = f"{config.api_username}:{password}"
                auth_bytes = auth_string.encode("utf-8")
                auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")
                headers["Authorization"] = f"Basic {auth_b64}"
        
        request_timeout = httpx.Timeout(timeout_seconds, connect=min(3.0, float(timeout_seconds)))
        async with httpx.AsyncClient(base_url=base_url, timeout=request_timeout, headers=headers) as client:
            response = await client.get(path)
            response.raise_for_status()
            data = _decode_api_response(response)
    except Exception as exc:
        api = container_info.setdefault("api", {})
        api.setdefault("endpoints", {})[endpoint_config.name] = {
            "ok": False,
            "status_code": getattr(getattr(exc, "response", None), "status_code", None),
            "path": path,
            "error": str(exc),
            "connectivity_error": _is_connectivity_error(exc),
        }
        LOGGER.warning(
            "API endpoint request failed name=%s endpoint=%s path=%s error=%s",
            source_name,
            endpoint_config.name,
            path,
            exc,
        )
        return []
    
    # Extract metrics from response
    metrics = _extract_metrics_from_response(data, endpoint_config.metric_prefix)
    api = container_info.setdefault("api", {})
    api.setdefault("metrics", {}).update(metrics)
    api.setdefault("endpoints", {})[endpoint_config.name] = {
        "ok": True,
        "status_code": response.status_code,
        "path": path,
        "data": data,
    }
    for metric_name, value in metrics.items():
        readings.append(Reading(
            source_type="myst",
            source_name=source_name,
            metric_name=metric_name,
            value=value,
            labels={},
            timestamp=timestamp,
            raw_data=container_info,
        ))
    
    return readings


def _extract_metrics_from_response(data: Any, prefix: str) -> Dict[str, float]:
    """Extract numeric metrics from API response data.
    
    Args:
        data: Response data
        prefix: Metric name prefix
        
    Returns:
        Dictionary of metric names and values
    """
    metrics: Dict[str, float] = {}
    
    def _extract(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_path = f"{path}_{key}" if path else key
                _extract(value, new_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                new_path = f"{path}_{i}" if path else str(i)
                _extract(item, new_path)
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            metric_name = f"{prefix}_{path}" if prefix and path else (prefix or path)
            metrics[metric_name] = float(obj)
        elif obj is True:
            metric_name = f"{prefix}_{path}" if prefix and path else (prefix or path)
            metrics[metric_name] = 1.0
        elif obj is False:
            metric_name = f"{prefix}_{path}" if prefix and path else (prefix or path)
            metrics[metric_name] = 0.0
    
    _extract(data)
    return metrics


def _decode_api_response(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


async def _fetch_api_endpoint_async(
    base_url: str,
    endpoint_config,
    auth: tuple[str, str] | None,
    source_name: str,
    enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return {"ok": False, "error": "disabled"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url}{endpoint_config.path}", auth=auth)
            response.raise_for_status()
            return {
                "ok": True,
                "status_code": response.status_code,
                "data": _decode_api_response(response),
                "connectivity_error": False,
            }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "source_name": source_name,
            "connectivity_error": _is_connectivity_error(exc),
        }


async def _probe_api_async(
    host: str,
    source_name: str,
    ports: dict[str, Any],
    config: MystCollectorConfig,
) -> dict[str, Any]:
    host_port = config.api_default_port
    port_entries = ports.get("4050/tcp") if isinstance(ports, dict) else None
    if isinstance(port_entries, list) and port_entries:
        host_port = int(port_entries[0].get("HostPort") or config.api_default_port)
    base_url = f"http://{host}:{host_port}"
    auth = _api_auth(config)
    result: dict[str, Any] = {
        "enabled": config.api_probe_enabled,
        "up": False,
        "auth": auth is not None,
        "schema_available": False,
        "endpoints": {},
        "metrics": {},
        "labels": {},
        "management": {},
    }
    try:
        async with httpx.AsyncClient() as client:
            health = await client.get(f"{base_url}/healthcheck", auth=auth)
            result["up"] = health.status_code == 200
            if result["up"]:
                data = _decode_api_response(health)
                result["endpoints"]["healthcheck"] = {
                    "ok": True,
                    "status_code": health.status_code,
                    "data": data,
                }
                extracted = extract_api_metrics("healthcheck", "health", data)
                result["metrics"].update(extracted["metrics"])
                result["labels"].update(extracted["labels"])
                result["management"].setdefault("health", {})["healthcheck"] = _redact_api_value(data)
    except Exception:
        return result
    if not result["up"]:
        return result

    endpoints = config.api_endpoints or _create_default_endpoints()
    for endpoint in endpoints:
        if endpoint.path in BLOCKED_ENDPOINTS or endpoint.path in SKIPPED_ENDPOINTS:
            continue
        if endpoint.path == "/healthcheck":
            continue
        endpoint_result = await _fetch_api_endpoint_async(base_url, endpoint, auth, source_name, True)
        result["endpoints"][endpoint.name] = endpoint_result
        if not endpoint_result.get("ok") and endpoint_result.get("connectivity_error"):
            break
        if endpoint_result.get("ok"):
            data = endpoint_result.get("data")
            category = getattr(endpoint, "category", None) or endpoint.metric_prefix
            extracted = extract_api_metrics(endpoint.name, category, data)
            result["metrics"].update(extracted["metrics"])
            result["labels"].update(extracted["labels"])
            result["management"].setdefault(category, {})[endpoint.name] = _redact_api_value(data)
            if endpoint.name == "identities" and isinstance(data, dict):
                identities = data.get("identities")
                if isinstance(identities, list) and identities and isinstance(identities[0], dict):
                    result["identity"] = identities[0].get("id")
    return result


def _tequilapi_summary(api_probe: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"identity": api_probe.get("identity")}
    management = api_probe.get("management") or {}

    location = (((management.get("location") or {}).get("location")) or {})
    if isinstance(location, dict):
        if location.get("ip") is not None:
            summary["public_ip"] = location.get("ip")

    nat = ((management.get("nat") or {}).get("nat_type")) or {}
    if isinstance(nat, dict):
        summary["nat_type"] = nat.get("type")
    elif nat is not None:
        summary["nat_type"] = nat

    services = ((management.get("services") or {}).get("services")) or {}
    if isinstance(services, dict):
        if services.get("count") is not None:
            summary["services_count"] = float(services["count"])
        if services.get("running_count") is not None:
            summary["services_running"] = float(services["running_count"])

    sessions = (management.get("sessions") or {})
    active = ((sessions.get("sessions") or {}).get("daily") or {}).get("count")
    if active is not None:
        summary["sessions_active"] = float(active)
    sessions_1d = ((sessions.get("session_stats_aggregated") or {}).get("daily") or {}).get("count")
    if sessions_1d is not None:
        summary["sessions_1d"] = float(sessions_1d)

    provider = ((management.get("provider") or {}).get("provider_quality")) or {}
    if isinstance(provider, dict) and provider.get("quality") is not None:
        summary["provider_quality"] = float(provider["quality"])

    payments = ((management.get("payments") or {}).get("transactor_fees_v2")) or {}
    human = ((((payments.get("current") or {}).get("settlement")) or {}).get("human")) if isinstance(payments, dict) else None
    if human is not None:
        summary["wallet_balance"] = human

    return summary


async def _collect_myst_nodes_async(config: MystCollectorConfig, timeout_seconds: int, log_window_seconds: int) -> list[dict[str, Any]]:
    readings = await collect_myst(config, timeout_seconds)
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for reading in readings:
        raw = reading.raw_data or {}
        key = str(raw.get("host") or raw.get("container_name") or reading.source_name)
        if key in seen:
            continue
        seen.add(key)
        node = dict(raw)
        node.setdefault("name", reading.source_name)
        nodes.append(node)
    return nodes


async def collect_myst_nodes_async(config: MystCollectorConfig, timeout_seconds: int, log_window_seconds: int) -> list[dict[str, Any]]:
    return await _collect_myst_nodes_async(config, timeout_seconds, log_window_seconds)
