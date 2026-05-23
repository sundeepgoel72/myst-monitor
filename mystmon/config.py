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


class MystCollectorConfig(BaseModel):
    enabled: bool = True
    docker_socket: str = "unix:///var/run/docker.sock"
    container_name_patterns: list[str] = Field(default_factory=lambda: [r"^myst(\.|$)", r"^myst\d+"])
    api_probe_enabled: bool = True
    api_probe_paths: list[str] = Field(default_factory=lambda: ["/healthcheck"])
    api_default_port: int = 4050
    containers: list[MystContainerConfig] = Field(default_factory=list)


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
    config_path = Path(path or os.getenv("MYSTMON_CONFIG", "config.yaml"))
    if not config_path.exists():
        return MystMonConfig()

    with config_path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle) or {}
    return MystMonConfig.model_validate(raw)
