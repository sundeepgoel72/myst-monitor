"""Mysterium node collector for retrieving metrics from TequilAPI endpoints.

This module provides functionality to collect metrics from Mysterium nodes
using information derived from the MystNodes portal rather than local Docker
discovery. It handles explicit host-based TequilAPI probing and metric collection
from various endpoints.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

from mystmon.config import (
    MystCollectorConfig, 
    MystContainerConfig, 
    MystRemoteHostConfig,
    TequilApiEndpointConfig
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
    "/nat/type",
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


async def collect_myst(config: MystCollectorConfig, timeout_seconds: int) -> List[Reading]:
    """Collect metrics from Mysterium nodes based on portal-derived information.
    
    Args:
        config: Collector configuration
        timeout_seconds: Request timeout in seconds
        
    Returns:
        List of readings from all nodes
    """
    readings: List[Reading] = []
    
    # Collect from portal-derived remote hosts
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
    host_info: Dict[str, Any],
) -> List[Reading]:
    """Probe TequilAPI endpoints.
    
    Args:
        base_url: Base URL for the API
        config: Collector configuration
        timeout_seconds: Request timeout in seconds
        host_info: Host information
        
    Returns:
        List of API readings
    """
    name = host_info["name"]
    timestamp = datetime.now()
    readings: List[Reading] = []
    
    # Check if API is accessible
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds) as client:
            response = await client.get("/healthcheck")
            api_up = response.status_code == 200
    except Exception:
        api_up = False

    host_info["running"] = api_up
    host_info["status"] = "running" if api_up else "unreachable"
    host_info["api"] = {
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
    
    readings.append(Reading(
        source_type="myst",
        source_name=name,
        metric_name="api_up",
        value=1.0 if api_up else 0.0,
        labels={},
        timestamp=timestamp,
        raw_data=host_info,
    ))
    
    if not api_up:
        return readings
    
    # Collect metrics from configured endpoints
    endpoints = config.api_endpoints or _create_default_endpoints()
    for endpoint_config in endpoints:
        if endpoint_config.path in BLOCKED_ENDPOINTS:
            continue
            
        try:
            endpoint_readings = await _fetch_api_endpoint(
                base_url, config, timeout_seconds, endpoint_config, name, timestamp, host_info
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
    host_info: Dict[str, Any],
) -> List[Reading]:
    """Fetch data from a single API endpoint.
    
    Args:
        base_url: Base URL for the API
        config: Collector configuration
        timeout_seconds: Request timeout in seconds
        endpoint_config: Endpoint configuration
        source_name: Source name for readings
        timestamp: Timestamp for readings
        host_info: Host information
        
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
            data = response.json()
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
    api = host_info.setdefault("api", {})
    api.setdefault("metrics", {}).update(metrics)
    api.setdefault("endpoints", {})[endpoint_config.name] = {
        "ok": True,
        "status_code": response.status_code,
        "path": path,
        "raw_data": data,  # Preserve the raw API response data
    }
    for metric_name, value in metrics.items():
        readings.append(Reading(
            source_type="myst",
            source_name=source_name,
            metric_name=metric_name,
            value=value,
            labels={},
            timestamp=timestamp,
            raw_data=host_info,
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
