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


class MystMonConfig(BaseModel):
    service: ServiceConfig = Field(default_factory=ServiceConfig)
    prometheus: PrometheusConfig = Field(default_factory=PrometheusConfig)
    snmp: SnmpConfig = Field(default_factory=SnmpConfig)


def load_config(path: str | os.PathLike[str] | None = None) -> MystMonConfig:
    config_path = Path(path or os.getenv("MYSTMON_CONFIG", "config.yaml"))
    if not config_path.exists():
        return MystMonConfig()

    with config_path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle) or {}
    return MystMonConfig.model_validate(raw)

