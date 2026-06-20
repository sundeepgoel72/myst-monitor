"""Mysterium node collector for retrieving metrics from TequilAPI endpoints."""

from __future__ import annotations

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

    # Configured hosts are kept only as a compatibility fallback when portal
    # inventory is unavailable.
    if not local_readings and not portal_nodes:
        readings.extend(await _collect_configured_containers(config, timeout_seconds))

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
    readings: List[Reading] = []
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
        host_info = {
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
        }
        base_url = f"http://{host}:{config.api_default_port}"
        probe_readings = await _probe_api(base_url, config, timeout_seconds, host_info)
        readings.extend(probe_readings)
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
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds) as client:
            response = await client.get("/healthcheck")
            api_up = response.status_code == 200
    except Exception:
        api_up = False

    container_info["running"] = api_up
    container_info["status"] = "running" if api_up else "unreachable"
    api = {
        "up": api_up,
        "metrics": {},
        "endpoints": {
            "healthcheck": {
                "ok": api_up,
                "status_code": 200 if api_up else None,
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
    
    # Collect metrics from configured endpoints
    endpoints = config.api_endpoints or _create_default_endpoints()
    for endpoint_config in endpoints:
        if endpoint_config.path in BLOCKED_ENDPOINTS or endpoint_config.path in SKIPPED_ENDPOINTS:
            continue
            
        try:
            endpoint_readings = await _fetch_api_endpoint(
                base_url, config, timeout_seconds, endpoint_config, name, timestamp, container_info
            )
            readings.extend(endpoint_readings)
        except Exception:
            LOGGER.warning(
                "API endpoint collection failed name=%s endpoint=%s path=%s",
                name,
                endpoint_config.name,
                endpoint_config.path,
            )
    
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
        
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds, headers=headers) as client:
            response = await client.get(path)
            response.raise_for_status()
            data = _decode_api_response(response)
    except Exception as exc:
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
