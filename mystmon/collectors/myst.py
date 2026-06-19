"""Mysterium node collector for retrieving metrics from TequilAPI endpoints.

This module provides functionality to collect metrics from Mysterium nodes
running locally or on remote hosts. It handles Docker container discovery,
TequilAPI endpoint probing, and metric collection from various endpoints.

The collector supports both local Docker containers and remote hosts with
configurable authentication and port settings.
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

from mystmon.config import MystCollectorConfig, MystContainerConfig, MystRemoteHostConfig
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
    "/connection/proxy/location",
    "/location",
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
    """Collect metrics from Mysterium nodes.
    
    Args:
        config: Collector configuration
        timeout_seconds: Request timeout in seconds
        
    Returns:
        List of readings from all nodes
    """
    readings: List[Reading] = []
    
    # Collect from local Docker containers
    if config.enabled:
        container_readings = await _collect_local_containers(config, timeout_seconds)
        readings.extend(container_readings)
    
    # Collect from remote hosts
    remote_readings = await _collect_remote_hosts(config, timeout_seconds)
    readings.extend(remote_readings)
    
    return readings


async def _collect_local_containers(config: MystCollectorConfig, timeout_seconds: int) -> List[Reading]:
    """Collect metrics from local Docker containers.
    
    Args:
        config: Collector configuration
        timeout_seconds: Request timeout in seconds
        
    Returns:
        List of readings from local containers
    """
    try:
        import docker
        client = docker.DockerClient(base_url=config.docker_socket)
        containers = client.containers.list(all=True)
    except Exception as exc:
        LOGGER.warning("Docker container listing failed reason=%s", exc)
        return []
    
    readings: List[Reading] = []
    for container in containers:
        if not _matches_container_patterns(container.name, config.container_name_patterns):
            continue
            
        container_info = _container_info(container)
        network_info = _container_networks(container)
        log_counts = _container_log_counts(container, config.service.log_window_seconds)
        
        # Add basic container metrics
        container_readings = _container_readings(container_info, network_info, log_counts)
        readings.extend(container_readings)
        
        # Probe TequilAPI if enabled
        if config.api_probe_enabled:
            api_readings = await _probe_container_api(container, config, timeout_seconds, container_info, network_info)
            readings.extend(api_readings)
    
    return readings


async def _collect_remote_hosts(config: MystCollectorConfig, timeout_seconds: int) -> List[Reading]:
    """Collect metrics from remote hosts.
    
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


def _matches_container_patterns(name: str, patterns: List[str]) -> bool:
    """Check if a container name matches any of the configured patterns.
    
    Args:
        name: Container name
        patterns: List of regex patterns
        
    Returns:
        True if name matches any pattern
    """
    return any(re.search(pattern, name) for pattern in patterns)


def _container_info(container) -> Dict[str, Any]:
    """Extract basic information from a Docker container.
    
    Args:
        container: Docker container object
        
    Returns:
        Dictionary with container information
    """
    return {
        "name": container.name,
        "container_name": container.name,
        "host": "localhost",
        "running": container.status == "running",
        "status": container.status,
        "restart_count": _extract_restart_count(container),
        "uptime_seconds": _calculate_uptime(container),
        "created_at": container.attrs.get("Created"),
    }


def _container_networks(container) -> List[Dict[str, Any]]:
    """Extract network information from a Docker container.
    
    Args:
        container: Docker container object
        
    Returns:
        List of network dictionaries
    """
    networks = []
    network_settings = container.attrs.get("NetworkSettings", {})
    for network_name, network_data in network_settings.get("Networks", {}).items():
        networks.append({
            "name": network_name,
            "ip_address": network_data.get("IPAddress"),
            "gateway": network_data.get("Gateway"),
            "mac_address": network_data.get("MacAddress"),
        })
    return networks


def _container_log_counts(container, log_window_seconds: int) -> Dict[str, int]:
    """Count log events in the recent window.
    
    Args:
        container: Docker container object
        log_window_seconds: Time window to analyze
        
    Returns:
        Dictionary with log counts by type
    """
    counts: Dict[str, int] = {}
    try:
        since = datetime.now() - timedelta(seconds=log_window_seconds)
        logs = container.logs(since=since, stderr=True, stdout=True)
        log_text = logs.decode("utf-8") if isinstance(logs, bytes) else str(logs)
        counts = {
            "error_or_warning": len(re.findall(r"\b(error|warning)\b", log_text, re.IGNORECASE)),
            "identity_warning": log_text.count("identity") + log_text.count("Identity"),
            "promise": log_text.count("promise") + log_text.count("Promise"),
            "session": log_text.count("session") + log_text.count("Session"),
        }
    except Exception:
        LOGGER.warning("Log analysis failed for container=%s", container.name)
    return counts


def _extract_restart_count(container) -> int:
    """Extract restart count from container attributes.
    
    Args:
        container: Docker container object
        
    Returns:
        Restart count
    """
    try:
        return int(container.attrs.get("RestartCount", 0))
    except (TypeError, ValueError):
        return 0


def _calculate_uptime(container) -> Optional[float]:
    """Calculate container uptime in seconds.
    
    Args:
        container: Docker container object
        
    Returns:
        Uptime in seconds or None
    """
    try:
        started_at = container.attrs.get("State", {}).get("StartedAt")
        if not started_at:
            return None
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        return (datetime.now(started.tzinfo) - started).total_seconds()
    except Exception:
        return None


def _container_readings(
    container_info: Dict[str, Any],
    network_info: List[Dict[str, Any]],
    log_counts: Dict[str, int],
) -> List[Reading]:
    """Create readings from container information.
    
    Args:
        container_info: Container information
        network_info: Network information
        log_counts: Log event counts
        
    Returns:
        List of readings
    """
    name = container_info["name"]
    timestamp = datetime.now()
    readings: List[Reading] = []
    
    # Basic container metrics
    readings.append(Reading(
        source_type="myst",
        source_name=name,
        metric_name="running",
        value=1.0 if container_info["running"] else 0.0,
        labels={},
        timestamp=timestamp,
        raw_data=container_info,
    ))
    
    readings.append(Reading(
        source_type="myst",
        source_name=name,
        metric_name="restart_count",
        value=float(container_info["restart_count"]),
        labels={},
        timestamp=timestamp,
        raw_data=container_info,
    ))
    
    if container_info["uptime_seconds"] is not None:
        readings.append(Reading(
            source_type="myst",
            source_name=name,
            metric_name="uptime_seconds",
            value=float(container_info["uptime_seconds"]),
            labels={},
            timestamp=timestamp,
            raw_data=container_info,
        ))
    
    # Log metrics
    for log_type, count in log_counts.items():
        readings.append(Reading(
            source_type="myst",
            source_name=name,
            metric_name=f"log_{log_type}",
            value=float(count),
            labels={},
            timestamp=timestamp,
            raw_data=container_info,
        ))
    
    return readings


async def _probe_container_api(
    container,
    config: MystCollectorConfig,
    timeout_seconds: int,
    container_info: Dict[str, Any],
    network_info: List[Dict[str, Any]],
) -> List[Reading]:
    """Probe TequilAPI for a container.
    
    Args:
        container: Docker container object
        config: Collector configuration
        timeout_seconds: Request timeout in seconds
        container_info: Container information
        network_info: Network information
        
    Returns:
        List of API readings
    """
    name = container_info["name"]
    
    # Determine API host and port
    api_host, api_port = _determine_api_host_port(container, config, network_info)
    if not api_host or not api_port:
        LOGGER.debug("Could not determine API host/port for container=%s", name)
        return []
    
    base_url = f"http://{api_host}:{api_port}"
    return await _probe_api(base_url, config, timeout_seconds, container_info)


def _determine_api_host_port(container, config: MystCollectorConfig, network_info: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[int]]:
    """Determine the API host and port for a container.
    
    Args:
        container: Docker container object
        config: Collector configuration
        network_info: Network information
        
    Returns:
        Tuple of (host, port) or (None, None)
    """
    # Check for explicitly configured container
    for container_config in config.containers:
        if container_config.name == container.name:
            if container_config.host and container_config.tequilapi_port:
                return container_config.host, container_config.tequilapi_port
            if container_config.tequilapi_port:
                return "localhost", container_config.tequilapi_port
    
    # Check for expected network
    if config.containers:
        for container_config in config.containers:
            if container_config.name == container.name and container_config.expected_network:
                for network in network_info:
                    if network["name"] == container_config.expected_network:
                        return network["ip_address"], config.api_default_port
    
    # Check for port range
    if config.containers:
        for container_config in config.containers:
            if container_config.name == container.name and container_config.expected_port_range:
                # This is a simplified implementation - in practice you'd parse the range
                return "localhost", config.api_default_port
    
    # Default to localhost if container is running
    if container.status == "running":
        return "localhost", config.api_default_port
    
    return None, None


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
    from mystmon.config import TequilApiEndpointConfig
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
