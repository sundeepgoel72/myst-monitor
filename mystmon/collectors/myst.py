from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import docker
import httpx

from mystmon.config import MystCollectorConfig

ERROR_PATTERN = re.compile(r"error|warn|failed|settle|auth|unlock|authentication needed", re.IGNORECASE)
WARNING_PATTERN = re.compile(r"authentication needed|failed to sign metrics|unlock", re.IGNORECASE)
PROMISE_PATTERN = re.compile(r"Received hermes promise|promise state updated", re.IGNORECASE)
SESSION_PATTERN = re.compile(r"session", re.IGNORECASE)


async def collect_myst_nodes(config: MystCollectorConfig, timeout_seconds: int, log_window_seconds: int) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_collect_myst_nodes_sync, config, timeout_seconds, log_window_seconds)


def _collect_myst_nodes_sync(
    config: MystCollectorConfig,
    timeout_seconds: int,
    log_window_seconds: int,
) -> list[dict[str, Any]]:
    client = docker.DockerClient(base_url=config.docker_socket, timeout=timeout_seconds)
    try:
        containers = [
            container
            for container in client.containers.list(all=True)
            if _is_myst_container(container.name, config.container_name_patterns)
        ]
        return [_container_snapshot(container, config, log_window_seconds) for container in containers]
    finally:
        client.close()


def _is_myst_container(name: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, name) for pattern in patterns)


def _container_snapshot(container: Any, config: MystCollectorConfig, log_window_seconds: int) -> dict[str, Any]:
    container.reload()
    attrs = container.attrs
    state = attrs.get("State", {})
    network_settings = attrs.get("NetworkSettings", {})
    networks = network_settings.get("Networks", {})
    ports = network_settings.get("Ports") or {}
    logs = _read_logs(container, log_window_seconds)
    api_probe = _probe_api(container.name, ports, config) if config.api_probe_enabled else None

    return {
        "name": container.name,
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
        "warnings": _warnings(logs),
    }


def summarize_logs(log_text: str) -> dict[str, int]:
    lines = log_text.splitlines()
    return {
        "error_or_warning": sum(1 for line in lines if ERROR_PATTERN.search(line)),
        "promise": sum(1 for line in lines if PROMISE_PATTERN.search(line)),
        "session": sum(1 for line in lines if SESSION_PATTERN.search(line)),
        "identity_warning": sum(1 for line in lines if WARNING_PATTERN.search(line)),
    }


def _read_logs(container: Any, since_seconds: int) -> str:
    try:
        since = datetime.now(UTC) - timedelta(seconds=since_seconds)
        raw = container.logs(since=since, stdout=True, stderr=True, tail=2000)
    except Exception as exc:
        return f"mystmon log read failed: {exc}"
    return raw.decode("utf-8", errors="replace")


def _probe_api(container_name: str, ports: dict[str, Any], config: MystCollectorConfig) -> dict[str, Any]:
    port = _configured_api_port(container_name, config) or _mapped_api_port(ports, config.api_default_port)
    if not port:
        return {"enabled": False, "reason": "no mapped TequilAPI port found"}

    url = f"http://127.0.0.1:{port}{config.api_probe_paths[0]}"
    try:
        response = httpx.get(url, timeout=3)
        return {
            "enabled": True,
            "url": url,
            "status_code": response.status_code,
            "up": response.is_success,
        }
    except httpx.HTTPError as exc:
        return {"enabled": True, "url": url, "up": False, "error": str(exc)}


def _configured_api_port(container_name: str, config: MystCollectorConfig) -> int | None:
    for item in config.containers:
        if item.name == container_name:
            return item.tequilapi_port
    return None


def _mapped_api_port(ports: dict[str, Any], api_default_port: int) -> int | None:
    for container_port, mappings in ports.items():
        if not container_port.startswith(f"{api_default_port}/") or not mappings:
            continue
        return int(mappings[0]["HostPort"])
    return None


def _image_name(attrs: dict[str, Any]) -> str:
    tags = attrs.get("Config", {}).get("Image")
    return str(tags or attrs.get("Image", "unknown"))


def _network_summary(networks: dict[str, Any]) -> list[dict[str, str]]:
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
    if not started_at:
        return 0
    normalized = started_at.replace("Z", "+00:00")
    try:
        started = datetime.fromisoformat(normalized)
    except ValueError:
        return 0
    return max(0, int((datetime.now(UTC) - started).total_seconds()))


def _warnings(log_text: str) -> list[str]:
    findings = []
    if re.search(r"authentication needed: password or unlock", log_text, re.IGNORECASE):
        findings.append("authentication needed: password or unlock")
    if re.search(r"failed to sign metrics", log_text, re.IGNORECASE):
        findings.append("failed to sign metrics")
    return findings
