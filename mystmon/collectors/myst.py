"""Mysterium node collector that integrates with MystNodes portal for authoritative node information."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import inspect
import subprocess
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from typing import Any

import httpx

from mystmon.config import MystCollectorConfig, MystNodesPortalAccountConfig, MystRemoteHostConfig, TequilApiEndpointConfig
from mystmon.collectors.mystnodes import collect_mystnodes_portal_accounts
from mystmon.storage import Reading

LOGGER = logging.getLogger(__name__)
ERROR_PATTERN = re.compile(r"error|warn|failed|settle|auth|unlock|authentication needed", re.IGNORECASE)
WARNING_PATTERN = re.compile(r"authentication needed|failed to sign metrics|unlock", re.IGNORECASE)
PROMISE_PATTERN = re.compile(r"Received hermes promise|promise state updated", re.IGNORECASE)
SESSION_PATTERN = re.compile(r"session", re.IGNORECASE)
READ_ONLY_PATHS = {
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
    "/settle/history",
    "/transactor/chains-summary",
    "/transactor/fees",
    "/v2/transactor/fees",
    "/config",
    "/config/default",
    "/location",
    "/connection/location",
    "/connection/proxy/location",
    "/nat/type",
}
BLOCKED_PREFIXES = (
    "/auth/",
    "/stop",
    "/feedback/",
    "/config/user",
    "/config/set",
    "/identities/create",
    "/identities/import",
    "/identities/register",
    "/identities/",
    "/services/",
    "/services",
    "/transactor/settle/",
    "/transactor/staking",
    "/transactor/rewards",
    "/transactor/payment-order",
    "/connection/",
    "/connection",
)
BLOCKED_PATHS = set(READ_ONLY_PATHS) | {
    "/connection",
    "/stop",
    "/feedback",
    "/bug-report",
    "/auth/login",
    "/auth/logout",
    "/identities/create",
    "/identities/import",
    "/identities/register",
    "/identities/{id}/unlock",
    "/config/set",
    "/config/user",
    "/settle/withdraw",
    "/settle/pay",
}


async def collect_myst(
    config: MystCollectorConfig,
    timeout_seconds: int,
    log_window_seconds: int | None = None,
    mystnodes_accounts: list[MystNodesPortalAccountConfig] | None = None,
) -> list[Reading]:
    """Collect MYST node snapshots and expose them as scheduler readings.

    The scheduler expects ``Reading`` objects, while the lower-level collector
    returns per-node dictionaries. This wrapper preserves the older public
    collector entrypoint and converts node snapshots into ``myst`` readings.
    """
    effective_log_window = log_window_seconds or getattr(config, "log_window_seconds", 21600)
    nodes = await collect_myst_nodes_async(
        config,
        timeout_seconds,
        effective_log_window,
        mystnodes_accounts=mystnodes_accounts,
    )
    collected_at = datetime.now(UTC)
    readings: list[Reading] = []
    for node in nodes:
        source_name = str(
            node.get("name")
            or node.get("container_name")
            or node.get("portal_identity")
            or node.get("host")
            or "unknown"
        )
        labels = {
            "container_name": str(node.get("container_name") or ""),
            "host": str(node.get("host") or ""),
            "status": str(node.get("status") or "unknown"),
        }
        readings.append(
            Reading(
                source_type="myst",
                source_name=source_name,
                metric_name="running",
                value=1.0 if node.get("running") else 0.0,
                labels=labels,
                timestamp=collected_at,
                raw_data=node,
            )
        )
    return readings

async def collect_myst_nodes_async(
    config: MystCollectorConfig,
    timeout_seconds: int,
    log_window_seconds: int,
    mystnodes_accounts: list[MystNodesPortalAccountConfig] | None = None,
) -> list[dict[str, Any]]:
    """Collect MYST nodes from local Docker, remote Docker hosts, and MystNodes portal.
    
    Args:
        config: Configuration for MYST collection
        timeout_seconds: Timeout for collection operations
        log_window_seconds: Time window for log analysis
        
    Returns:
        List of node information dictionaries
    """
    return await _collect_myst_nodes_async(config, timeout_seconds, log_window_seconds, mystnodes_accounts=mystnodes_accounts)


async def _collect_myst_nodes_async(
    config: MystCollectorConfig,
    timeout_seconds: int,
    log_window_seconds: int,
    mystnodes_accounts: list[MystNodesPortalAccountConfig] | None = None,
) -> list[dict[str, Any]]:
    """Internal implementation of MYST node collection.
    
    First collects MystNodes portal accounts to get authoritative list of nodes and their local IPs,
    then collects local and remote Docker containers, and finally probes TequilAPI using portal data.
    
    Args:
        config: Configuration for MYST collection
        timeout_seconds: Timeout for collection operations
        log_window_seconds: Time window for log analysis
        
    Returns:
        List of node information dictionaries
    """
    # First, collect MystNodes portal accounts to get the authoritative list of nodes and their local IPs
    portal_nodes_data = []
    enabled_accounts = []
    enabled_account_indices = []
    
    # Track which accounts are enabled and their original indices
    accounts = mystnodes_accounts if mystnodes_accounts is not None else getattr(config, "mystnodes_accounts", [])
    if accounts:
        for i, account in enumerate(accounts):
            if account.enabled:
                enabled_accounts.append(account)
                enabled_account_indices.append(i)
    
    if enabled_accounts:
        try:
            portal_nodes_data = await collect_mystnodes_portal_accounts(
                configs=enabled_accounts,
                timeout_seconds=timeout_seconds,
                local_nodes=None  # We'll match later
            )
        except Exception as exc:
            LOGGER.error("Failed to collect MystNodes portal data: %s", exc)
            portal_nodes_data = []
    if portal_nodes_data is None:
        portal_nodes_data = []
    
    # Flatten portal nodes data and preserve account information
    portal_nodes = []
    account_mapping = {}  # Map identity to account info
    
    # Process only enabled accounts and their results, using the correct original indices
    for i, account_data in enumerate(portal_nodes_data):
        # Get the original index for this enabled account
        if i < len(enabled_account_indices):
            original_index = enabled_account_indices[i]
            account_config = accounts[original_index] if original_index < len(accounts) else None
            account_info = {
                'account': account_config.account if account_config else 'unknown',
                'enabled': account_config.enabled if account_config else True
            }
        else:
            account_info = {'account': 'unknown', 'enabled': True}
        
        if isinstance(account_data, list):
            for node in account_data:
                if isinstance(node, dict) and 'identity' in node:
                    portal_nodes.append(node)
                    account_mapping[node['identity']] = account_info
        elif isinstance(account_data, dict):
            if 'identity' in account_data:
                portal_nodes.append(account_data)
                account_mapping[account_data['identity']] = account_info
            elif 'nodes' in account_data and isinstance(account_data['nodes'], list):
                for node in account_data['nodes']:
                    if isinstance(node, dict) and 'identity' in node:
                        portal_nodes.append(node)
                        account_mapping[node['identity']] = account_info
    
    # Create a mapping of identity to local IP and account info for TequilAPI probing
    identity_to_local_ip = {}
    identity_to_node_info = {}
    identity_to_account = {}
    
    for node in portal_nodes:
        if isinstance(node, dict) and 'identity' in node and 'localIp' in node:
            identity = node['identity']
            identity_to_local_ip[identity] = node['localIp']
            identity_to_node_info[identity] = node
            identity_to_account[identity] = account_mapping.get(identity, {'account': 'unknown', 'enabled': True})
    
    try:
        import docker
    except ImportError:
        LOGGER.warning("MYST Docker collection skipped reason=missing_docker_dependency")
        remote_nodes = await _collect_remote_nodes(config, timeout_seconds, identity_to_local_ip, identity_to_node_info, identity_to_account)
        return remote_nodes

    try:
        client = docker.DockerClient(base_url=config.docker_socket, timeout=timeout_seconds)
    except Exception as exc:
        LOGGER.warning("MYST Docker collection skipped reason=docker_unavailable error=%s", exc)
        remote_nodes = await _collect_remote_nodes(config, timeout_seconds, identity_to_local_ip, identity_to_node_info, identity_to_account)
        return remote_nodes

    try:
        containers = [
            container
            for container in client.containers.list(all=True)
            if _is_myst_container(container.name, config.container_name_patterns)
        ]
        local_tasks = [_container_snapshot_async(container, config, log_window_seconds, identity_to_local_ip, identity_to_node_info, identity_to_account) for container in containers]
        local_nodes = await asyncio.gather(*local_tasks)
        remote_nodes = await _collect_remote_nodes(config, timeout_seconds, identity_to_local_ip, identity_to_node_info, identity_to_account)
        return list(local_nodes) + remote_nodes
    finally:
        client.close()


def _is_myst_container(name: str, patterns: list[str]) -> bool:
    """Check if a container name matches MYST container patterns.
    
    Args:
        name: Container name to check
        patterns: List of regex patterns to match against
        
    Returns:
        True if the container name matches any pattern
    """
    return any(re.search(pattern, name) for pattern in patterns)


async def _container_snapshot_async(container: Any, config: MystCollectorConfig, log_window_seconds: int, 
                                   identity_to_local_ip: dict[str, str], identity_to_node_info: dict[str, dict],
                                   identity_to_account: dict[str, dict]) -> dict[str, Any]:
    """Create a snapshot of a Docker container's state and TequilAPI data.
    
    Args:
        container: Docker container object
        config: Configuration for MYST collection
        log_window_seconds: Time window for log analysis
        identity_to_local_ip: Mapping of identity to local IP address
        identity_to_node_info: Mapping of identity to node information
        identity_to_account: Mapping of identity to account information
        
    Returns:
        Dictionary containing container snapshot data
    """
    container.reload()
    attrs = container.attrs
    state = attrs.get("State", {})
    network_settings = attrs.get("NetworkSettings", {})
    networks = network_settings.get("Networks", {})
    ports = network_settings.get("Ports") or {}
    logs = _read_logs(container, log_window_seconds)
    
    # Extract identity from container
    container_identity = _extract_identity_from_container(container.name)
    
    # Get account information for this identity
    account_info = identity_to_account.get(container_identity) if container_identity else None
    
    # Use ONLY portal's localIp as the API host - no fallbacks per handover requirements
    api_host = identity_to_local_ip.get(container_identity) if container_identity else None
    
    # If we don't have a localIp from the portal, we cannot probe the API
    api_probe = None
    if api_host and config.api_probe_enabled:
        try:
            api_probe = await _probe_api_async(api_host, container.name, ports, config, networks=networks)
        except Exception as e:
            LOGGER.error(f"API probe failed for node {container.name} with localIp {api_host}: {e}")
            api_probe = {"enabled": False, "reason": f"API probe failed: {e}"}

    node_name = _node_display_name(container.name, api_probe)
    return {
        "name": node_name,
        "container_name": container.name,
        "host": api_host,
        "id": container.short_id,
        "image": _image_name(attrs),
        "running": state.get("Running", False),
        "status": state.get("Status", "unknown"),
        "restart_count": int(attrs.get("RestartCount", 0)),
        "started_at": state.get("StartedAt"),
        "uptime_seconds": _uptime_seconds(state.get("StartedAt")) if state.get("Running") else 0,
        "networks": _network_summary(networks),
        "ports": _port_summary(ports),
        "log_counts": summarize_logs(logs),
        "api": api_probe,
        **_tequilapi_summary(api_probe),
        "warnings": _warnings(logs),
        "portal_identity": container_identity,
        "portal_local_ip": identity_to_local_ip.get(container_identity),
        "portal_data": identity_to_node_info.get(container_identity) if container_identity else None,
        "portal_account": account_info['account'] if account_info else None,
        "portal_account_enabled": account_info['enabled'] if account_info else True,
    }


def _extract_identity_from_container(container_name: str) -> str | None:
    """Extract identity from container name (assuming format myst-<identity>).
    
    Args:
        container_name: Name of the Docker container
        
    Returns:
        Identity string or None if not found
    """
    if container_name.startswith('myst-'):
        return container_name[5:]  # Remove 'myst-' prefix
    return None


async def _collect_remote_nodes(config: MystCollectorConfig, timeout_seconds: int, 
                               identity_to_local_ip: dict[str, str], identity_to_node_info: dict[str, dict],
                               identity_to_account: dict[str, dict]) -> list[dict[str, Any]]:
    """Collect MYST nodes from remote Docker hosts.
    
    Args:
        config: Configuration for MYST collection
        timeout_seconds: Timeout for collection operations
        identity_to_local_ip: Mapping of identity to local IP address
        identity_to_node_info: Mapping of identity to node information
        identity_to_account: Mapping of identity to account information
        
    Returns:
        List of remote node information dictionaries
    """
    nodes: list[dict[str, Any]] = []
    for host_config in config.remote_hosts:
        if not host_config.enabled:
            continue
        nodes.extend(await _collect_remote_host_nodes(host_config, config, timeout_seconds, identity_to_local_ip, identity_to_node_info, identity_to_account))
    return nodes


async def _collect_remote_host_nodes(
    host_config: MystRemoteHostConfig,
    config: MystCollectorConfig,
    timeout_seconds: int,
    identity_to_local_ip: dict[str, str],
    identity_to_node_info: dict[str, dict],
    identity_to_account: dict[str, dict],
) -> list[dict[str, Any]]:
    """Collect MYST nodes from a specific remote Docker host.
    
    Args:
        host_config: Configuration for the remote host
        config: Configuration for MYST collection
        timeout_seconds: Timeout for collection operations
        identity_to_local_ip: Mapping of identity to local IP address
        identity_to_node_info: Mapping of identity to node information
        identity_to_account: Mapping of identity to account information
        
    Returns:
        List of node information dictionaries from the remote host
    """
    password = os.getenv(host_config.password_env) if host_config.password_env else None
    if host_config.password_env and not password:
        LOGGER.error(
            "MYST collection failed host=%s reason=missing_ssh_password env=%s",
            host_config.host,
            host_config.password_env,
        )
        return [_remote_error_node(host_config.host, "missing SSH password environment variable")]

    pattern = "|".join(config.container_name_patterns)
    remote_command = (
        "docker ps -a --format '{{.Names}}' "
        f"| grep -Ei '{pattern}' "
        "| while read -r c; do docker inspect \"$c\" --format '{{json .}}'; done"
    )
    command = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"ConnectTimeout={timeout_seconds}",
        f"{host_config.user}@{host_config.host}",
        remote_command,
    ]
    env = os.environ.copy()
    if password:
        command = ["sshpass", "-e", *command]
        env["SSHPASS"] = password

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            env=env,
            text=True,
            timeout=timeout_seconds + 5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        LOGGER.exception(
            "MYST collection failed host=%s reason=remote_inventory_error error=%s",
            host_config.host,
            exc,
        )
        return [_remote_error_node(host_config.host, str(exc))]

    if completed.returncode != 0:
        error = completed.stderr.strip() or "remote SSH inventory failed"
        LOGGER.error(
            "MYST collection failed host=%s reason=remote_inventory_nonzero returncode=%s error=%s",
            host_config.host,
            completed.returncode,
            error,
        )
        return [_remote_error_node(host_config.host, error)]

    nodes: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        attrs = json.loads(line)
        state = attrs.get("State", {})
        networks = attrs.get("NetworkSettings", {}).get("Networks", {})
        container_name = attrs.get("Name", "").lstrip("/")
        
        # Extract identity from container
        container_identity = _extract_identity_from_container(container_name)
        
        # Get account information for this identity
        account_info = identity_to_account.get(container_identity) if container_identity else None
        
        # Use ONLY portal's localIp as the API host - no fallbacks per handover requirements
        api_host = identity_to_local_ip.get(container_identity) if container_identity else None
        
        # If we don't have a localIp from the portal, we cannot probe the API
        api_probe = None
        if api_host and config.api_probe_enabled:
            try:
                api_port = host_config.tequilapi_port or config.api_default_port
                api_probe = await _probe_api_async(
                    api_host,
                    container_name,
                    attrs.get("NetworkSettings", {}).get("Ports") or {},
                    config,
                    api_port,
                    networks=networks,
                )
            except Exception as e:
                LOGGER.error(f"API probe failed for node {container_name} with localIp {api_host}: {e}")
                api_probe = {"enabled": False, "reason": f"API probe failed: {e}"}
        
        node_name = _node_display_name(container_name, api_probe)
        nodes.append(
            {
                "name": node_name,
                "container_name": container_name,
                "host": api_host,
                "inventory_host": host_config.host,
                "id": str(attrs.get("Id", ""))[:12],
                "image": _image_name(attrs),
                "running": state.get("Running", False),
                "status": state.get("Status", "unknown"),
                "restart_count": int(attrs.get("RestartCount", 0)),
                "started_at": state.get("StartedAt"),
                "uptime_seconds": _uptime_seconds(state.get("StartedAt")) if state.get("Running") else 0,
                "networks": _network_summary(networks),
                "ports": _port_summary(attrs.get("NetworkSettings", {}).get("Ports") or {}),
                "log_counts": {"error_or_warning": 0, "promise": 0, "session": 0, "identity_warning": 0},
                "api": api_probe,
                **_tequilapi_summary(api_probe),
                "warnings": [],
                "portal_identity": container_identity,
                "portal_local_ip": identity_to_local_ip.get(container_identity),
                "portal_data": identity_to_node_info.get(container_identity) if container_identity else None,
                "portal_account": account_info['account'] if account_info else None,
                "portal_account_enabled": account_info['enabled'] if account_info else True,
            }
        )
    if not nodes:
        LOGGER.error(
            "MYST collection failed host=%s reason=no_remote_containers_found",
            host_config.host,
        )
        return [_remote_error_node(host_config.host, "no MYST containers found")]
    return nodes


def _remote_error_node(host: str, reason: str) -> dict[str, Any]:
    """Create a placeholder node for remote collection errors.
    
    Args:
        host: Host that failed collection
        reason: Reason for the failure
        
    Returns:
        Dictionary representing an error node
    """
    return {
        "name": f"unreachable-{host}",
        "container_name": "",
        "host": host,
        "id": "",
        "image": "",
        "running": False,
        "status": "unreachable",
        "restart_count": 0,
        "started_at": None,
        "uptime_seconds": 0,
        "networks": [],
        "ports": [],
        "log_counts": {"error_or_warning": 1, "promise": 0, "session": 0, "identity_warning": 0},
        "api": {"enabled": False, "reason": reason},
        "warnings": [reason],
    }


def summarize_logs(log_text: str) -> dict[str, int]:
    """Summarize log text by counting different types of log entries.
    
    Args:
        log_text: Text content of logs to analyze
        
    Returns:
        Dictionary with counts of different log types
    """
    lines = log_text.splitlines()
    return {
        "error_or_warning": sum(1 for line in lines if ERROR_PATTERN.search(line)),
        "promise": sum(1 for line in lines if PROMISE_PATTERN.search(line)),
        "session": sum(1 for line in lines if SESSION_PATTERN.search(line)),
        "identity_warning": sum(1 for line in lines if WARNING_PATTERN.search(line)),
    }


def _read_logs(container: Any, since_seconds: int) -> str:
    """Read logs from a Docker container.
    
    Args:
        container: Docker container object
        since_seconds: Time window in seconds to read logs from
        
    Returns:
        Log text content
    """
    try:
        since = datetime.now(UTC) - timedelta(seconds=since_seconds)
        raw = container.logs(since=since, stdout=True, stderr=True, tail=2000)
    except Exception as exc:
        LOGGER.exception(
            "MYST log read failed container=%s reason=container_logs_error error=%s",
            getattr(container, "name", "unknown"),
            exc,
        )
        return f"mystmon log read failed: {exc}"
    return raw.decode("utf-8", errors="replace")


async def _probe_api_async(
    api_host: str,
    container_name: str,
    ports: dict[str, Any],
    config: MystCollectorConfig,
    override_port: int | None = None,
    networks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Probe TequilAPI endpoints for a node.
    
    Args:
        api_host: Host address to probe
        container_name: Name of the container being probed
        ports: Port mappings for the container
        config: Configuration for MYST collection
        override_port: Port to use instead of default
        networks: Network information for the container
        
    Returns:
        Dictionary containing API probe results
    """
    port = override_port or config.api_default_port
    if not port:
        LOGGER.info("MYST API probe skipped container=%s reason=no mapped TequilAPI port found", container_name)
        return {"enabled": False, "reason": "no mapped TequilAPI port found"}

    auth = _api_auth(config)
    base_url = f"http://{api_host}:{port}"

    endpoints: dict[str, Any] = {}
    numeric_metrics: dict[str, float] = {}
    labels: dict[str, str] = {}
    management_data: dict[str, Any] = {}

    for endpoint in config.api_endpoints:
        endpoint_path = _normalize_path(endpoint.path)
        if not _is_read_only_path(endpoint_path):
            endpoints[endpoint.name] = _endpoint_result(endpoint, endpoint_path, ok=False, reason="blocked_for_safety", supported=False)
            continue

        endpoint_result = await _fetch_api_endpoint_async(base_url, endpoint, auth, container_name, True)
        endpoint_result["supported"] = True
        endpoint_result["category"] = endpoint.category
        endpoint_result["last_check"] = datetime.now(UTC).isoformat()
        endpoints[endpoint.name] = endpoint_result

        # Handle endpoint status classification for diagnostics
        status_code = endpoint_result.get("status_code")
        is_ok = endpoint_result.get("ok", False)
        
        # Classify endpoint status for diagnostics
        if status_code == 400:
            endpoint_result["diagnostic_status"] = "runtime_error"
        elif status_code == 404:
            endpoint_result["diagnostic_status"] = "not_found"
        elif is_ok:
            endpoint_result["diagnostic_status"] = "ok"
        else:
            endpoint_result["diagnostic_status"] = "error"

        # Extract data from any successful read-only endpoint even when schema discovery failed.
        if is_ok:
            extracted = extract_api_metrics(endpoint.name, endpoint.metric_prefix, endpoint_result.get("data"))
            numeric_metrics.update(extracted["metrics"])
            labels.update(extracted["labels"])
            _merge_management(management_data, endpoint.category, endpoint.name, endpoint_result.get("data"))

    health = endpoints.get("healthcheck", {})
    return {
        "enabled": True,
        "base_url": base_url,
        "up": bool(health.get("ok")),
        "status_code": health.get("status_code"),
        "auth": auth is not None,
        "schema_available": False,
        "last_check": datetime.now(UTC).isoformat(),
        "endpoints": endpoints,
        "metrics": numeric_metrics,
        "labels": labels,
        "management": management_data,
        "identity": _api_identity(endpoints, labels),
    }
def _normalize_path(path: str) -> str:
    """Normalize a URL path by stripping trailing slashes.
    
    Args:
        path: URL path to normalize
        
    Returns:
        Normalized path
    """
    return urlsplit(path).path.rstrip("/") or "/"


def _path_matches(actual: str, supported: str) -> bool:
    """Check if an actual path matches a supported path pattern.
    
    Args:
        actual: Actual path to check
        supported: Supported path pattern
        
    Returns:
        True if paths match
    """
    actual_parts = [part for part in _normalize_path(actual).split("/") if part]
    supported_parts = [part for part in _normalize_path(supported).split("/") if part]
    if len(actual_parts) != len(supported_parts):
        return False
    for actual_part, supported_part in zip(actual_parts, supported_parts):
        if supported_part.startswith("{") and supported_part.endswith("}"):
            continue
        if supported_part.startswith(":"):
            continue
        if actual_part != supported_part:
            return False
    return True


def _is_read_only_path(path: str) -> bool:
    """Check if a path is a read-only TequilAPI endpoint.
    
    Args:
        path: Path to check
        
    Returns:
        True if path is read-only
    """
    path = _normalize_path(path)
    if path in READ_ONLY_PATHS:
        return True
    if path.startswith("/services/") and re.fullmatch(r"/services/[^/]+", path):
        return False
    return any(path == read_only or path.startswith(f"{read_only}/") for read_only in READ_ONLY_PATHS)


def _endpoint_result(endpoint: TequilApiEndpointConfig, path: str, ok: bool, reason: str | None, supported: bool) -> dict[str, Any]:
    """Create a standardized result dictionary for an endpoint.
    
    Args:
        endpoint: Endpoint configuration
        path: Endpoint path
        ok: Whether the endpoint call was successful
        reason: Reason for failure if not ok
        supported: Whether the endpoint is supported
        
    Returns:
        Dictionary with endpoint result information
    """
    return {
        "url": path,
        "ok": ok,
        "reason": reason,
        "supported": supported,
        "category": endpoint.category,
        "last_check": datetime.now(UTC).isoformat(),
    }


def _merge_management(management: dict[str, Any], category: str, endpoint_name: str, data: Any) -> None:
    """Merge endpoint data into management data structure by category.
    
    Args:
        management: Management data dictionary to merge into
        category: Category to merge under
        endpoint_name: Name of the endpoint
        data: Data to merge
    """
    bucket = management.setdefault(category, {})
    bucket[endpoint_name] = _normalize_management_value(category, endpoint_name, data)


def _normalize_management_value(category: str, endpoint_name: str, data: Any) -> Any:
    """Normalize management data for a specific category and endpoint.
    
    Args:
        category: Data category
        endpoint_name: Name of the endpoint
        data: Raw data to normalize
        
    Returns:
        Normalized data
    """
    redacted = _redact_api_value(data)
    if category == "health" and isinstance(redacted, dict):
        return {
            "uptime": redacted.get("uptime"),
            "version": redacted.get("version"),
            "build_info": redacted.get("build_info") or redacted.get("buildInfo"),
        }
    if category == "identities":
        identities = _list_from_payload(redacted, "identities") if isinstance(redacted, (dict, list)) else None
        if identities is not None:
            return {"count": len(identities), "identities": identities}
    if category == "services":
        services = _list_from_payload(redacted, "services") if isinstance(redacted, (dict, list)) else None
        if services is None and isinstance(redacted, list):
            services = redacted
        if services is not None:
            return {
                "count": len(services),
                "running_count": sum(1 for service in services if _truthy_service_running(service)),
                "types": sorted({str(service.get("type")) for service in services if isinstance(service, dict) and service.get("type")}),
            }
    if category == "sessions":
        if isinstance(redacted, dict):
            return {
                "active": redacted.get("active") or redacted.get("count"),
                "count": redacted.get("count"),
                "daily": redacted.get("daily") or redacted.get("stats") or redacted,
            }
        if isinstance(redacted, list):
            return {"count": len(redacted)}
    if category == "provider":
        if isinstance(redacted, dict):
            return {
                "quality": redacted.get("quality"),
                "activity": redacted.get("activity"),
                "sessions": redacted.get("sessions"),
                "transferred_data": redacted.get("transferredData") or redacted.get("transferred_data"),
                "service_earnings": redacted.get("serviceEarnings") or redacted.get("service_earnings"),
            }
    if category in {"payments", "settlements"}:
        return redacted
    if category in {"config", "location", "nat"}:
        return redacted
    return redacted


def _node_display_name(container_name: str, api_probe: dict[str, Any] | None) -> str:
    """Determine the display name for a node.
    
    Args:
        container_name: Name of the Docker container
        api_probe: API probe results
        
    Returns:
        Display name for the node
    """
    if api_probe:
        identity = api_probe.get("identity")
        if identity:
            return str(identity)
        labels = api_probe.get("labels") or {}
        for key in ("identity_id", "provider_id", "node_id", "status_id"):
            if labels.get(key):
                return str(labels[key])
    return container_name


def _api_identity(endpoints: dict[str, Any], labels: dict[str, str]) -> str | None:
    """Extract node identity from API endpoints and labels.
    
    Args:
        endpoints: Dictionary of endpoint results
        labels: Dictionary of label data
        
    Returns:
        Identity string or None if not found
    """
    identity = _identity_from_endpoint(endpoints.get("identities", {}).get("data"))
    if identity:
        return identity
    for key in ("identity_id", "provider_id", "node_id", "status_id"):
        if labels.get(key):
            return labels[key]
    return None


def _identity_from_endpoint(data: Any) -> str | None:
    """Extract identity from endpoint data.
    
    Args:
        data: Endpoint data to extract identity from
        
    Returns:
        Identity string or None if not found
    """
    identities = _list_from_payload(data, "identities")
    if not identities:
        if isinstance(data, dict):
            return _first_string_value(data, ("id", "identity", "provider_id", "providerId", "node_id", "nodeId"))
        return None
    first = identities[0]
    if isinstance(first, dict):
        return _first_string_value(first, ("id", "identity", "provider_id", "providerId", "node_id", "nodeId", "address"))
    if isinstance(first, str):
        return first
    return None


def _tequilapi_summary(api_probe: dict[str, Any] | None) -> dict[str, Any]:
    """Create a summary of TequilAPI probe results.
    
    Args:
        api_probe: API probe results
        
    Returns:
        Dictionary with summarized API data
    """
    if not api_probe:
        return {
            "identity": None,
            "public_ip": None,
            "location": None,
            "nat_type": None,
            "services_count": None,
            "services_running": None,
            "service_types": None,
            "service_quality": None,
            "sessions_active": None,
            "sessions_1d": None,
            "sessions_7d": None,
            "provider_quality": None,
            "provider_transferred_data": None,
            "provider_service_earnings": None,
            "payments_balance": None,
            "settlements_count": None,
        }
    management = api_probe.get("management") or {}
    identities = _first_category_payload(management.get("identities"), ("identities",))
    sessions_bucket = management.get("sessions") or {}
    sessions = _first_category_payload(sessions_bucket, ("session_stats_aggregated", "sessions_stats_daily", "sessions"))
    session_details = _first_category_payload(sessions_bucket, ("sessions",))
    provider = _first_category_payload(management.get("provider"), ("provider_quality", "provider_activity_stats", "provider_service_earnings", "provider_sessions_1d", "provider_sessions_7d"))
    services = _first_category_payload(management.get("services"), ("services",))
    location = _first_location_payload(management.get("location"))
    nat = _first_nat_payload(management.get("nat"))
    payments = _first_category_payload(management.get("payments"), ("transactor_fees_v2", "transactor_fees"))
    settlements = management.get("settlements") or {}

    identity = api_probe.get("identity") or _first_string_value(identities if isinstance(identities, dict) else {}, ("identity", "id"))
    public_ip = _first_string_value(location or {}, ("ip", "public_ip", "publicIp", "address"))
    service_types = services.get("types") if isinstance(services, dict) else None

    return {
        "identity": identity,
        "public_ip": public_ip,
        "location": location,
        "nat_type": _first_string_value(nat or {}, ("type", "nat_type", "natType")) if isinstance(nat, dict) else (str(nat) if nat else None),
        "services_count": _first_number_value(services, ("count",)),
        "services_running": _first_number_value(services, ("running_count",)),
        "service_types": service_types,
        "service_quality": _first_value(provider, ("service_quality", "quality")),
        "sessions_active": _session_active_value(session_details) or _session_active_value(sessions),
        "sessions_1d": _extract_bucket_value(sessions, "1d") or _provider_range_value(provider, "1d"),
        "sessions_7d": _extract_bucket_value(sessions, "7d") or _provider_range_value(provider, "7d"),
        "provider_quality": _first_number_value(provider, ("quality",)),
        "provider_transferred_data": _first_number_value(provider, ("transferred_data",)),
        "provider_service_earnings": _first_number_value(provider, ("service_earnings",)),
        "payments_balance": _first_number_value(payments, ("balance",)),
        "settlements_count": _collection_count(settlements),
    }


def _first_location_payload(value: Any) -> dict[str, Any] | None:
    """Extract the first location payload from nested data.
    
    Args:
        value: Data to extract location from
        
    Returns:
        Location data dictionary or None
    """
    if isinstance(value, dict):
        for key in ("location", "connection_location", "connection_proxy_location"):
            nested = value.get(key)
            if isinstance(nested, dict):
                return nested
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return _first_location_payload(item)
    return None


def _first_category_payload(value: Any, preferred_keys: tuple[str, ...]) -> dict[str, Any] | None:
    """Extract the first payload from a category with preferred key ordering.
    
    Args:
        value: Data to extract from
        preferred_keys: Preferred keys to look for first
        
    Returns:
        Payload data dictionary or None
    """
    if isinstance(value, dict):
        for key in preferred_keys:
            nested = value.get(key)
            if isinstance(nested, dict):
                return nested
        for nested in value.values():
            if isinstance(nested, dict):
                return nested
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return _first_category_payload(item, preferred_keys)
    return None


def _first_nat_payload(value: Any) -> dict[str, Any] | None:
    """Extract the first NAT payload from nested data.
    
    Args:
        value: Data to extract NAT information from
        
    Returns:
        NAT data dictionary or None
    """
    if isinstance(value, dict):
        for key in ("nat_type", "natType", "type"):
            nested = value.get(key)
            if isinstance(nested, dict):
                return nested
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return _first_nat_payload(item)
    return None


def _first_dict_value(value: Any) -> dict[str, Any] | None:
    """Extract the first dictionary value from data.
    
    Args:
        value: Data to extract dictionary from
        
    Returns:
        First dictionary found or None
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return None


def _first_value(data: dict[str, Any] | None, keys: tuple[str, ...]) -> Any:
    """Extract the first value for specified keys from data.
    
    Args:
        data: Data dictionary to extract from
        keys: Keys to look for
        
    Returns:
        First value found or None
    """
    if not isinstance(data, dict):
        return None
    for key in keys:
        if key in data:
            return data.get(key)
    return None


def _first_number_value(data: Any, keys: tuple[str, ...]) -> float | None:
    """Extract the first numeric value for specified keys from data.
    
    Args:
        data: Data to extract from
        keys: Keys to look for
        
    Returns:
        First numeric value found or None
    """
    if not isinstance(data, dict):
        return _first_numeric(data)
    for key in keys:
        numeric = _first_numeric(data.get(key))
        if numeric is not None:
            return numeric
    return None


def _collection_count(value: Any) -> float | None:
    """Get a count from collection data.
    
    Args:
        value: Data to count
        
    Returns:
        Count as float or None
    """
    if isinstance(value, dict):
        for key in ("count", "total", "length", "size"):
            numeric = _first_numeric(value.get(key))
            if numeric is not None:
                return numeric
        return float(len(value))
    if isinstance(value, list):
        return float(len(value))
    return _first_numeric(value)


def _first_numeric(value: Any) -> float | None:
    """Extract the first numeric value from data.
    
    Args:
        value: Data to extract numeric value from
        
    Returns:
        Numeric value as float or None
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for item in value.values():
            numeric = _first_numeric(item)
            if numeric is not None:
                return numeric
    if isinstance(value, list):
        for item in value:
            numeric = _first_numeric(item)
            if numeric is not None:
                return numeric
    return None


def _extract_bucket_value(data: Any, bucket: str) -> float | None:
    """Extract a value from a time bucket in data.
    
    Args:
        data: Data to extract from
        bucket: Time bucket name (e.g., "1d", "7d")
        
    Returns:
        Bucket value as float or None
    """
    if not isinstance(data, dict):
        return None
    for key in (
        bucket,
        f"stats_{bucket}",
        f"stats{bucket}",
        f"{bucket}_count",
        f"{bucket}Count",
        "daily",
    ):
        numeric = _first_numeric(data.get(key))
        if numeric is not None:
            return numeric
    return None


def _provider_range_value(provider: Any, bucket: str) -> float | None:
    """Extract a range value from provider data.
    
    Args:
        provider: Provider data to extract from
        bucket: Time bucket name (e.g., "1d", "7d")
        
    Returns:
        Range value as float or None
    """
    if not isinstance(provider, dict):
        return None
    for key in ("sessions", "activity", "transferred_data", "service_earnings"):
        value = provider.get(key)
        if isinstance(value, dict):
            numeric = _extract_bucket_value(value, bucket)
            if numeric is not None:
                return numeric
    return None


def _session_active_value(sessions: Any) -> float | None:
    """Extract active session count from sessions data.
    
    Args:
        sessions: Sessions data to extract from
        
    Returns:
        Active session count as float or None
    """
    if not isinstance(sessions, dict):
        return None
    for key in ("active", "count"):
        numeric = _first_numeric(sessions.get(key))
        if numeric is not None:
            return numeric
    daily = sessions.get("daily")
    if isinstance(daily, dict):
        for key in ("count", "active", "sessions"):
            numeric = _first_numeric(daily.get(key))
            if numeric is not None:
                return numeric
    return None


def _first_string_value(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Extract the first string value for specified keys from data.
    
    Args:
        data: Data dictionary to extract from
        keys: Keys to look for
        
    Returns:
        First string value found or None
    """
    for key in keys:
        value = data.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            return str(value)
    return None


async def _fetch_api_endpoint_async(
    base_url: str,
    endpoint: TequilApiEndpointConfig,
    auth: tuple[str, str] | None,
    container_name: str,
    is_supported: bool = True,
) -> dict[str, Any]:
    """Fetch data from a specific TequilAPI endpoint.
    
    Args:
        base_url: Base URL for the API
        endpoint: Endpoint configuration
        auth: Authentication credentials
        container_name: Name of the container being probed
        is_supported: Whether the endpoint is supported
        
    Returns:
        Dictionary with endpoint response data
    """
    # Only allow GET requests for safety
    if endpoint.method.upper() != "GET":
        return {
            "url": f"{base_url}{endpoint.path}",
            "ok": False,
            "reason": "method_not_allowed_for_safety",
            "supported": is_supported,
            "category": endpoint.category,
            "last_check": datetime.now(UTC).isoformat(),
        }
    
    url = f"{base_url}{endpoint.path}"
    LOGGER.info("MYST API call container=%s endpoint=%s url=%s", container_name, endpoint.name, url)
    try:
        async with httpx.AsyncClient() as client:
            response = client.get(url, timeout=3, auth=auth)
            if inspect.isawaitable(response):
                response = await response
            if response.status_code in {401, 403, 404, 405}:
                result = {
                    "url": url,
                    "status_code": response.status_code,
                    "ok": False,
                    "reason": _api_reason(response.status_code),
                    "supported": is_supported,
                    "category": endpoint.category,
                    "last_check": datetime.now(UTC).isoformat(),
                }
                _log_api_result(container_name, endpoint.name, result)
                return result
            response.raise_for_status()
            result = {
                "url": url,
                "status_code": response.status_code,
                "ok": True,
                "data": _decode_response(response),
                "supported": is_supported,
                "category": endpoint.category,
                "last_check": datetime.now(UTC).isoformat(),
            }
            _log_api_result(container_name, endpoint.name, result)
            return result
    except httpx.HTTPError as exc:
        result = {
            "url": url,
            "ok": False,
            "error": str(exc),
            "supported": is_supported,
            "category": endpoint.category,
            "last_check": datetime.now(UTC).isoformat(),
        }
        LOGGER.error(
            "MYST API call failed container=%s endpoint=%s url=%s reason=http_error error=%s",
            container_name,
            endpoint.name,
            url,
            exc,
        )
        _log_api_result(container_name, endpoint.name, result)
        return result


def _log_api_result(container_name: str, endpoint_name: str, result: dict[str, Any]) -> None:
    """Log API result information.
    
    Args:
        container_name: Name of the container
        endpoint_name: Name of the endpoint
        result: API result data to log
    """
    log_payload = {
        "ok": result.get("ok"),
        "status_code": result.get("status_code"),
        "reason": result.get("reason"),
        "error": result.get("error"),
        "data": _redact_api_value(result.get("data")),
    }
    LOGGER.info(
        "MYST API result container=%s endpoint=%s result=%s",
        container_name,
        endpoint_name,
        json.dumps(log_payload, sort_keys=True, default=str),
    )


def _redact_api_value(value: Any, max_chars: int = 2000) -> Any:
    """Redact sensitive information from API values.
    
    Args:
        value: Value to redact
        max_chars: Maximum characters to keep in non-sensitive strings
        
    Returns:
        Redacted value
    """
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
        # Redact sensitive data patterns
        if re.search(r"\b0x[a-fA-F0-9]{40}\b", value):
            return False
        sensitive_patterns = [
            r"(?<!0x)[a-zA-Z0-9]{32,}",  # Long alphanumeric strings
            r"password|secret|token|private|key|mnemonic|wallet|hash",  # Keywords
        ]
        
        lower_value = value.lower()
        for pattern in sensitive_patterns:
            if re.search(pattern, lower_value):
                return "***REDACTED***"
        return value if len(value) <= max_chars else f"{value[:max_chars]}...<truncated>"
    return value


def _contains_sensitive_data(value: str) -> bool:
    """Check if a string contains sensitive data that should be redacted.
    
    Args:
        value: String to check
        
    Returns:
        True if string contains sensitive data
    """
    if re.search(r"\b0x[a-fA-F0-9]{40}\b", value):
        return False
    sensitive_patterns = [
        r"(?<!0x)[a-zA-Z0-9]{32,}",  # Long alphanumeric strings
        r"password|secret|token|private|key|mnemonic|wallet|hash",  # Keywords
    ]
    
    lower_value = value.lower()
    for pattern in sensitive_patterns:
        if re.search(pattern, lower_value):
            return True
    return False


def _is_log_safe_key(key: str) -> bool:
    """Check if a key is safe to log (doesn't contain sensitive information).
    
    Args:
        key: Key to check
        
    Returns:
        True if key is safe to log
    """
    lowered = key.lower()
    blocked = ("password", "secret", "token", "private", "key", "mnemonic", "email", "wallet", "hash", "address")
    return not any(item in lowered for item in blocked)


def _api_auth(config: MystCollectorConfig) -> tuple[str, str] | None:
    """Get API authentication credentials from configuration.
    
    Args:
        config: Configuration containing authentication settings
        
    Returns:
        Tuple of (username, password) or None if not configured
    """
    if not config.api_username or not config.api_password_env:
        return None
    password = os.getenv(config.api_password_env)
    if not password:
        return None
    return (config.api_username, password)


def _api_reason(status_code: int) -> str:
    """Get a human-readable reason for an API status code.
    
    Args:
        status_code: HTTP status code
        
    Returns:
        Human-readable reason string
    """
    return {
        401: "unauthorized",
        403: "forbidden",
        404: "not found",
        405: "method not allowed",
    }.get(status_code, "unavailable")


def _decode_response(response: httpx.Response) -> Any:
    """Decode an HTTP response.
    
    Args:
        response: HTTP response to decode
        
    Returns:
        Decoded response data
    """
    content_type = getattr(response, "headers", {}).get("content-type", "")
    if "json" in content_type.lower():
        return response.json()
    try:
        return response.json()
    except ValueError:
        return response.text


def extract_api_metrics(endpoint_name: str, metric_prefix: str, data: Any) -> dict[str, dict[str, float | str]]:
    """Extract metrics from API endpoint data.
    
    Args:
        endpoint_name: Name of the endpoint
        metric_prefix: Prefix for metric names
        data: Data to extract metrics from
        
    Returns:
        Dictionary with metrics and labels
    """
    metrics: dict[str, float] = {}
    labels: dict[str, str] = {}

    if endpoint_name == "healthcheck" and isinstance(data, dict):
        metrics[f"{metric_prefix}_up"] = 1
        metrics[f"{metric_prefix}_uptime_seconds"] = float(_parse_go_duration(data.get("uptime", "")))
        if isinstance(data.get("process"), (int, float)):
            metrics[f"{metric_prefix}_process"] = float(data["process"])
        _add_label(labels, f"{metric_prefix}_version", data.get("version"))
        build_info = data.get("build_info") or data.get("buildInfo") or {}
        if isinstance(build_info, dict):
            _add_label(labels, f"{metric_prefix}_build_commit", build_info.get("commit"))
            _add_label(labels, f"{metric_prefix}_build_branch", build_info.get("branch"))
            _add_label(labels, f"{metric_prefix}_build_number", build_info.get("build_number") or build_info.get("buildNumber"))
        return {"metrics": metrics, "labels": labels}

    if endpoint_name == "identities":
        identities = _list_from_payload(data, "identities")
        if identities is not None:
            metrics[f"{metric_prefix}_count"] = float(len(identities))
        return {"metrics": metrics, "labels": labels}

    if endpoint_name == "services":
        services = _list_from_payload(data, "services")
        if services is not None:
            metrics[f"{metric_prefix}_count"] = float(len(services))
            metrics[f"{metric_prefix}_running_count"] = float(sum(1 for service in services if _truthy_service_running(service)))
        return {"metrics": metrics, "labels": labels}

    if endpoint_name in ["sessions", "session_stats_aggregated"]:
        # Extract session metrics
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (int, float)):
                    metrics[f"{metric_prefix}_{key}"] = float(value)
        elif isinstance(data, list):
            metrics[f"{metric_prefix}_count"] = float(len(data))
        return {"metrics": metrics, "labels": labels}

    if endpoint_name in ["provider_stats", "provider_sessions_1d", "provider_sessions_7d"]:
        # Extract provider metrics
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (int, float)):
                    metrics[f"{metric_prefix}_{key}"] = float(value)
                elif isinstance(value, str):
                    _add_label(labels, f"{metric_prefix}_{key}", value)
        return {"metrics": metrics, "labels": labels}

    if endpoint_name in ["payments_balance", "settlement_history"]:
        # Extract payment/settlement metrics
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (int, float)):
                    metrics[f"{metric_prefix}_{key}"] = float(value)
        return {"metrics": metrics, "labels": labels}

    if endpoint_name in ["location", "nat_type"]:
        # Extract location/NAT info as labels
        if isinstance(data, dict):
            for key, value in data.items():
                if not isinstance(value, (dict, list)):
                    _add_label(labels, f"{metric_prefix}_{key}", value)
        elif isinstance(data, str):
            _add_label(labels, metric_prefix, data)
        return {"metrics": metrics, "labels": labels}

    # Generic flattening for other endpoints
    flattened = _flatten_numeric(data)
    for key, value in flattened.items():
        metrics[f"{metric_prefix}_{key}"] = value
    if isinstance(data, dict):
        for key in ("type", "ip", "country", "status", "state"):
            _add_label(labels, f"{metric_prefix}_{key}", data.get(key))

    return {"metrics": metrics, "labels": labels}


def _parse_go_duration(value: str) -> int:
    """Parse a Go duration string into seconds.
    
    Args:
        value: Go duration string (e.g., "1h30m45s")
        
    Returns:
        Duration in seconds
    """
    if not value:
        return 0
    total = 0.0
    for amount, unit in re.findall(r"(\d+(?:\.\d+)?)(ns|µs|us|ms|h|m|s)", value):
        number = float(amount)
        if unit == "h":
            total += number * 3600
        elif unit == "m":
            total += number * 60
        elif unit == "s":
            total += number
        elif unit == "ms":
            total += number / 1000
        elif unit in {"us", "µs"}:
            total += number / 1_000_000
        elif unit == "ns":
            total += number / 1_000_000_000
    return int(total)


def _list_from_payload(data: Any, key: str) -> list[Any] | None:
    """Extract a list from payload data.
    
    Args:
        data: Data to extract from
        key: Key to look for the list under
        
    Returns:
        List or None if not found
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return data[key]
    return None


def _truthy_service_running(service: Any) -> bool:
    """Check if a service is running based on its data.
    
    Args:
        service: Service data to check
        
    Returns:
        True if service is running
    """
    if not isinstance(service, dict):
        return False
    for key in ("running", "enabled", "active"):
        if isinstance(service.get(key), bool):
            return service[key]
    status = service.get("status") or service.get("state")
    return str(status).lower() in {"running", "active", "started", "up"}


def _flatten_numeric(data: Any, prefix: str = "") -> dict[str, float]:
    """Flatten nested data structure into numeric metrics.
    
    Args:
        data: Data to flatten
        prefix: Prefix for metric names
        
    Returns:
        Dictionary of flattened numeric metrics
    """
    metrics: dict[str, float] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            name = _metric_key(prefix, key)
            metrics.update(_flatten_numeric(value, name))
    elif isinstance(data, list):
        metrics[_metric_key(prefix, "count")] = float(len(data))
        for index, value in enumerate(data[:10]):
            metrics.update(_flatten_numeric(value, _metric_key(prefix, str(index))))
    elif isinstance(data, bool):
        metrics[prefix] = 1.0 if data else 0.0
    elif isinstance(data, (int, float)):
        metrics[prefix] = float(data)
    return {key: value for key, value in metrics.items() if key}


def _metric_key(prefix: str, key: str) -> str:
    """Create a standardized metric key name.
    
    Args:
        prefix: Prefix for the key
        key: Base key name
        
    Returns:
        Standardized metric key
    """
    raw = f"{prefix}_{key}" if prefix else str(key)
    return re.sub(r"[^a-zA-Z0-9_]", "_", raw).strip("_").lower()


def _add_label(labels: dict[str, str], key: str, value: Any) -> None:
    """Add a label to the labels dictionary after redacting sensitive data.
    
    Args:
        labels: Dictionary to add label to
        key: Label key
        value: Label value
    """
    if value is None or isinstance(value, (dict, list)):
        return
    # Redact sensitive label values
    str_value = str(value)
    if _contains_sensitive_data(str_value):
        str_value = "***REDACTED***"
    labels[_metric_key("", key)] = str_value


def _configured_api_port(container_name: str, config: MystCollectorConfig, networks: dict[str, Any] | None = None) -> int | None:
    """Get the configured API port for a container.
    
    Args:
        container_name: Name of the container
        config: Configuration containing container settings
        networks: Network information for the container
        
    Returns:
        Configured port number or None
    """
    for item in config.containers:
        if _matches_configured_container(item.name, item.expected_network, container_name, networks):
            return item.tequilapi_port
    return None


def _configured_api_host(container_name: str, config: MystCollectorConfig, networks: dict[str, Any] | None = None) -> str | None:
    """Get the configured API host for a container.
    
    Args:
        container_name: Name of the container
        config: Configuration containing container settings
        networks: Network information for the container
        
    Returns:
        Configured host address or None
    """
    for item in config.containers:
        if _matches_configured_container(item.name, item.expected_network, container_name, networks):
            return item.host
    return None


def _matches_configured_container(
    configured_name: str,
    expected_network: str | None,
    container_name: str,
    networks: dict[str, Any] | None = None,
) -> bool:
    """Check if a container matches configured settings.
    
    Args:
        configured_name: Configured container name
        expected_network: Expected network name
        container_name: Actual container name
        networks: Network information
        
    Returns:
        True if container matches configuration
    """
    if configured_name != container_name:
        return False
    if not expected_network:
        return True
    return expected_network in (networks or {})


def _network_api_host(networks: dict[str, Any]) -> str | None:
    """Get API host from network information.
    
    Args:
        networks: Network information
        
    Returns:
        Host IP address or None
    """
    preferred_prefixes = ("ipvlan", "vlan")
    for prefix in preferred_prefixes:
        for name, details in networks.items():
            if not name.lower().startswith(prefix):
                continue
            ip_address = str(details.get("IPAddress", "")).strip()
            if ip_address:
                return ip_address
    for details in networks.values():
        ip_address = str(details.get("IPAddress", "")).strip()
        if ip_address:
            return ip_address
    return None


def _mapped_api_port(ports: dict[str, Any], api_default_port: int) -> int | None:
    """Get mapped API port from port mappings.
    
    Args:
        ports: Port mappings
        api_default_port: Default API port
        
    Returns:
        Mapped port number or None
    """
    for container_port, mappings in ports.items():
        if not container_port.startswith(f"{api_default_port}/") or not mappings:
            continue
        return int(mappings[0]["HostPort"])
    return None


def _image_name(attrs: dict[str, Any]) -> str:
    """Get the image name from container attributes.
    
    Args:
        attrs: Container attributes
        
    Returns:
        Image name
    """
    tags = attrs.get("Config", {}).get("Image")
    return str(tags or attrs.get("Image", "unknown"))


def _network_summary(networks: dict[str, Any]) -> list[dict[str, str]]:
    """Create a summary of network information.
    
    Args:
        networks: Network information
        
    Returns:
        List of network summary dictionaries
    """
    return [
        {
            "name": name,
            "ip_address": str(details.get("IPAddress", "")),
            "gateway": str(details.get("Gateway", "")),
            "mac_address": str(details.get("MacAddress", "")),
        }
        for name, details in networks.items()
    ]


def _port_summary(ports: dict[str, Any]) -> list[dict[str, str]]:
    """Create a summary of port mappings.
    
    Args:
        ports: Port mappings
        
    Returns:
        List of port summary dictionaries
    """
    summary: list[dict[str, str]] = []
    for container_port, mappings in ports.items():
        if not mappings:
            summary.append({"container_port": container_port, "host_ip": "", "host_port": ""})
            continue
        for mapping in mappings:
            summary.append(
                {
                    "container_port": container_port,
                    "host_ip": str(mapping.get("HostIp", "")),
                    "host_port": str(mapping.get("HostPort", "")),
                }
            )
    return summary


def _uptime_seconds(started_at: str | None) -> int:
    """Calculate uptime in seconds from start time.
    
    Args:
        started_at: ISO format start time string
        
    Returns:
        Uptime in seconds
    """
    if not started_at:
        return 0
    normalized = started_at.replace("Z", "+00:00")
    try:
        started = datetime.fromisoformat(normalized)
    except ValueError:
        return 0
    return max(0, int((datetime.now(UTC) - started).total_seconds()))


def _warnings(log_text: str) -> list[str]:
    """Extract warnings from log text.
    
    Args:
        log_text: Log text to analyze
        
    Returns:
        List of warning messages
    """
    findings = []
    if re.search(r"authentication needed: password or unlock", log_text, re.IGNORECASE):
        findings.append("authentication needed: password or unlock")
    if re.search(r"failed to sign metrics", log_text, re.IGNORECASE):
        findings.append("failed to sign metrics")
    return findings


collect_myst_nodes = collect_myst_nodes_async
