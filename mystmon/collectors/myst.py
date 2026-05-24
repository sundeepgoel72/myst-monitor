from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta
from typing import Any

import docker
import httpx

from mystmon.config import MystCollectorConfig, MystRemoteHostConfig, TequilApiEndpointConfig

LOGGER = logging.getLogger(__name__)
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
        local_nodes = [_container_snapshot(container, config, log_window_seconds) for container in containers]
        return local_nodes + _collect_remote_nodes(config, timeout_seconds)
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

    node_name = _node_display_name(container.name, api_probe)
    return {
        "name": node_name,
        "container_name": container.name,
        "host": config.local_host,
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


def _collect_remote_nodes(config: MystCollectorConfig, timeout_seconds: int) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for host_config in config.remote_hosts:
        if not host_config.enabled:
            continue
        nodes.extend(_collect_remote_host_nodes(host_config, config, timeout_seconds))
    return nodes


def _collect_remote_host_nodes(
    host_config: MystRemoteHostConfig,
    config: MystCollectorConfig,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    password = os.getenv(host_config.password_env) if host_config.password_env else None
    if host_config.password_env and not password:
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
        return [_remote_error_node(host_config.host, str(exc))]

    if completed.returncode != 0:
        return [_remote_error_node(host_config.host, completed.stderr.strip() or "remote SSH inventory failed")]

    nodes: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        attrs = json.loads(line)
        state = attrs.get("State", {})
        networks = attrs.get("NetworkSettings", {}).get("Networks", {})
        container_name = attrs.get("Name", "").lstrip("/")
        nodes.append(
            {
                "name": container_name,
                "container_name": container_name,
                "host": host_config.host,
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
                "api": {"enabled": False, "reason": "remote API probing disabled"},
                "warnings": [],
            }
        )
    if not nodes:
        return [_remote_error_node(host_config.host, "no MYST containers found")]
    return nodes


def _remote_error_node(host: str, reason: str) -> dict[str, Any]:
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
        LOGGER.info("MYST API probe skipped container=%s reason=no mapped TequilAPI port found", container_name)
        return {"enabled": False, "reason": "no mapped TequilAPI port found"}

    auth = _api_auth(config)
    base_url = f"http://127.0.0.1:{port}"
    endpoints: dict[str, Any] = {}
    numeric_metrics: dict[str, float] = {}
    labels: dict[str, str] = {}

    for endpoint in config.api_endpoints:
        endpoint_result = _fetch_api_endpoint(base_url, endpoint, auth, container_name)
        endpoints[endpoint.name] = endpoint_result
        if not endpoint_result.get("ok"):
            continue
        extracted = extract_api_metrics(endpoint.name, endpoint.metric_prefix, endpoint_result.get("data"))
        numeric_metrics.update(extracted["metrics"])
        labels.update(extracted["labels"])

    health = endpoints.get("healthcheck", {})
    return {
        "enabled": True,
        "base_url": base_url,
        "up": bool(health.get("ok")),
        "status_code": health.get("status_code"),
        "endpoints": endpoints,
        "metrics": numeric_metrics,
        "labels": labels,
        "identity": _api_identity(endpoints, labels),
    }


def _node_display_name(container_name: str, api_probe: dict[str, Any] | None) -> str:
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
    identity = _identity_from_endpoint(endpoints.get("identities", {}).get("data"))
    if identity:
        return identity
    for key in ("identity_id", "provider_id", "node_id", "status_id"):
        if labels.get(key):
            return labels[key]
    return None


def _identity_from_endpoint(data: Any) -> str | None:
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


def _first_string_value(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = data.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            return str(value)
    return None


def _fetch_api_endpoint(
    base_url: str,
    endpoint: TequilApiEndpointConfig,
    auth: tuple[str, str] | None,
    container_name: str,
) -> dict[str, Any]:
    url = f"{base_url}{endpoint.path}"
    LOGGER.info("MYST API call container=%s endpoint=%s url=%s", container_name, endpoint.name, url)
    try:
        response = httpx.get(url, timeout=3, auth=auth)
        if response.status_code in {401, 403, 404, 405}:
            result = {
                "url": url,
                "status_code": response.status_code,
                "ok": False,
                "reason": _api_reason(response.status_code),
            }
            _log_api_result(container_name, endpoint.name, result)
            return result
        response.raise_for_status()
        result = {
            "url": url,
            "status_code": response.status_code,
            "ok": True,
            "data": _decode_response(response),
        }
        _log_api_result(container_name, endpoint.name, result)
        return result
    except httpx.HTTPError as exc:
        result = {
            "url": url,
            "ok": False,
            "error": str(exc),
        }
        _log_api_result(container_name, endpoint.name, result)
        return result


def _log_api_result(container_name: str, endpoint_name: str, result: dict[str, Any]) -> None:
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
    if isinstance(value, dict):
        return {key: _redact_api_value(item, max_chars) for key, item in value.items() if _is_log_safe_key(str(key))}
    if isinstance(value, list):
        return [_redact_api_value(item, max_chars) for item in value[:20]]
    if isinstance(value, str):
        return value if len(value) <= max_chars else f"{value[:max_chars]}...<truncated>"
    return value


def _is_log_safe_key(key: str) -> bool:
    lowered = key.lower()
    blocked = ("password", "secret", "token", "private", "key", "mnemonic")
    return not any(item in lowered for item in blocked)


def _api_auth(config: MystCollectorConfig) -> tuple[str, str] | None:
    if not config.api_username or not config.api_password_env:
        return None
    password = os.getenv(config.api_password_env)
    if not password:
        return None
    return (config.api_username, password)


def _api_reason(status_code: int) -> str:
    return {
        401: "unauthorized",
        403: "forbidden",
        404: "not found",
        405: "method not allowed",
    }.get(status_code, "unavailable")


def _decode_response(response: httpx.Response) -> Any:
    content_type = response.headers.get("content-type", "")
    if "json" in content_type.lower():
        return response.json()
    try:
        return response.json()
    except ValueError:
        return response.text


def extract_api_metrics(endpoint_name: str, metric_prefix: str, data: Any) -> dict[str, dict[str, float | str]]:
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

    flattened = _flatten_numeric(data)
    for key, value in flattened.items():
        metrics[f"{metric_prefix}_{key}"] = value
    if isinstance(data, dict):
        for key in ("type", "ip", "country", "status", "state"):
            _add_label(labels, f"{metric_prefix}_{key}", data.get(key))

    return {"metrics": metrics, "labels": labels}


def _parse_go_duration(value: str) -> int:
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
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return data[key]
    return None


def _truthy_service_running(service: Any) -> bool:
    if not isinstance(service, dict):
        return False
    for key in ("running", "enabled", "active"):
        if isinstance(service.get(key), bool):
            return service[key]
    status = service.get("status") or service.get("state")
    return str(status).lower() in {"running", "active", "started", "up"}


def _flatten_numeric(data: Any, prefix: str = "") -> dict[str, float]:
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
    raw = f"{prefix}_{key}" if prefix else str(key)
    return re.sub(r"[^a-zA-Z0-9_]", "_", raw).strip("_").lower()


def _add_label(labels: dict[str, str], key: str, value: Any) -> None:
    if value is None or isinstance(value, (dict, list)):
        return
    labels[_metric_key("", key)] = str(value)


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
