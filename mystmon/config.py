from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, HttpUrl, field_validator


class ServiceConfig(BaseModel):
    name: str = "mystmon"
    poll_interval_seconds: int = Field(default=21600, ge=60)
    request_timeout_seconds: int = Field(default=10, ge=1)
    data_dir: str = "/data/mystmon"
    log_window_seconds: int = Field(default=21600, ge=60)


class PrometheusTarget(BaseModel):
    name: str
    url: HttpUrl


class PrometheusConfig(BaseModel):
    enabled: bool = True
    targets: list[PrometheusTarget] = Field(default_factory=list)


class SnmpTarget(BaseModel):
    name: str
    host: str
    port: int = Field(default=161, ge=1, le=65535)
    community: str | None = None
    oids: dict[str, str] = Field(default_factory=dict)

    @field_validator("oids")
    @classmethod
    def require_oids(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("SNMP targets must define at least one OID")
        return value


class SnmpConfig(BaseModel):
    enabled: bool = True
    default_community: str = "public"
    targets: list[SnmpTarget] = Field(default_factory=list)


class MystContainerConfig(BaseModel):
    name: str
    host: str = "192.168.1.72"
    expected_network: str | None = None
    expected_port_range: str | None = None
    tequilapi_port: int | None = None


class MystRemoteHostConfig(BaseModel):
    host: str
    user: str = "sundeep"
    password_env: str | None = None
    enabled: bool = True


class TequilApiEndpointConfig(BaseModel):
    name: str
    path: str
    metric_prefix: str


class MystCollectorConfig(BaseModel):
    enabled: bool = True
    local_host: str = "192.168.1.72"
    docker_socket: str = "unix:///var/run/docker.sock"
    container_name_patterns: list[str] = Field(default_factory=lambda: [r"^myst(\.|$)", r"^myst[0-9]"])
    api_probe_enabled: bool = True
    api_default_port: int = 4050
    api_username: str | None = None
    api_password_env: str | None = None
    api_endpoints: list[TequilApiEndpointConfig] = Field(
        default_factory=lambda: [
            TequilApiEndpointConfig(name="healthcheck", path="/healthcheck", metric_prefix="health"),
            TequilApiEndpointConfig(name="identities", path="/identities", metric_prefix="identities"),
            TequilApiEndpointConfig(name="services", path="/services", metric_prefix="services"),
            TequilApiEndpointConfig(
                name="session_stats_aggregated",
                path="/sessions/stats/aggregated",
                metric_prefix="sessions",
            ),
            TequilApiEndpointConfig(
                name="provider_sessions_1d",
                path="/node/provider/sessions-count?range=1d",
                metric_prefix="provider_sessions_1d",
            ),
            TequilApiEndpointConfig(
                name="provider_sessions_7d",
                path="/node/provider/sessions-count?range=7d",
                metric_prefix="provider_sessions_7d",
            ),
            TequilApiEndpointConfig(name="location", path="/location", metric_prefix="location"),
            TequilApiEndpointConfig(name="nat_type", path="/nat/type", metric_prefix="nat"),
        ]
    )
    containers: list[MystContainerConfig] = Field(default_factory=list)
    remote_hosts: list[MystRemoteHostConfig] = Field(default_factory=list)


class OutputConfig(BaseModel):
    latest_json_path: str = "/data/mystmon/latest.json"
    snmp_extend_path: str = "/data/mystmon/snmp_extend.txt"


class MystMonConfig(BaseModel):
    service: ServiceConfig = Field(default_factory=ServiceConfig)
    prometheus: PrometheusConfig = Field(default_factory=PrometheusConfig)
    snmp: SnmpConfig = Field(default_factory=SnmpConfig)
    myst: MystCollectorConfig = Field(default_factory=MystCollectorConfig)
    outputs: OutputConfig = Field(default_factory=OutputConfig)


def load_config(path: str | os.PathLike[str] | None = None) -> MystMonConfig:
    inline_config = os.getenv("MYSTMON_CONFIG_YAML")
    if inline_config:
        raw_inline: dict[str, Any] = yaml.safe_load(inline_config) or {}
        return MystMonConfig.model_validate(raw_inline)

    config_path = Path(path or os.getenv("MYSTMON_CONFIG", "config.yaml"))
    if not config_path.exists():
        return MystMonConfig()

    with config_path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle) or {}
    return MystMonConfig.model_validate(raw)
