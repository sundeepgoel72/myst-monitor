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
    default_community: str = "community"
    targets: list[SnmpTarget] = Field(default_factory=list)


class MystContainerConfig(BaseModel):
    name: str
    host: str = "localhost"
    expected_network: str | None = None
    expected_port_range: str | None = None
    tequilapi_port: int | None = None


class MystRemoteHostConfig(BaseModel):
    host: str
    user: str = "username"
    password_env: str | None = None
    enabled: bool = True


class TequilApiEndpointConfig(BaseModel):
    name: str
    path: str
    metric_prefix: str


class MystCollectorConfig(BaseModel):
    enabled: bool = True
    local_host: str = "localhost"
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


class MystNodesPortalEndpointConfig(BaseModel):
    name: str
    method: str = "GET"
    path: str
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)


class MystNodesPortalConfig(BaseModel):
    enabled: bool = False
    base_url: str = "https://my.mystnodes.com"
    email_env: str = "MYSTNODES_EMAIL"
    password_env: str = "MYSTNODES_PASSWORD"
    wallet_address: str | None = "0x9A183F79b7b803DF658DB0aC6159f0016e9db4bE"
    remember: bool = True
    request_delay_seconds: float = Field(default=1.0, ge=0)
    retry_count: int = Field(default=2, ge=0)
    retry_delay_seconds: float = Field(default=2.0, ge=0)
    node_detail_enabled: bool = True
    node_services_enabled: bool = False
    node_totals_enabled: bool = True
    node_totals_days: int = Field(default=30, ge=1)
    endpoints: list[MystNodesPortalEndpointConfig] = Field(
        default_factory=lambda: [
            MystNodesPortalEndpointConfig(name="me", path="/api/v2/me"),
            MystNodesPortalEndpointConfig(
                name="nodes",
                path="/api/v2/node",
                params={"page": 1, "itemsPerPage": 100},
            ),
            MystNodesPortalEndpointConfig(name="total_earnings", path="/api/v2/node/total-earnings"),
            MystNodesPortalEndpointConfig(
                name="total_transferred",
                path="/api/v2/node/total-transferred",
                params={"days": 30},
            ),
            MystNodesPortalEndpointConfig(
                name="earnings_30d",
                path="/api/v2/node/earnings",
                params={"days": 30},
            ),
        ]
    )


class OutputConfig(BaseModel):
    latest_json_path: str = "/data/mystmon/latest.json"
    snmp_extend_path: str = "/data/mystmon/snmp_extend.txt"


class HistoryConfig(BaseModel):
    enabled: bool = True
    db_path: str = "/data/mystmon/mystmon.db"


class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    chat_id_env: str = "TELEGRAM_CHAT_ID"
    report_time_local: str = "08:00"
    timezone: str = "Asia/Kolkata"
    disable_notification: bool = False


class MystMonConfig(BaseModel):
    service: ServiceConfig = Field(default_factory=ServiceConfig)
    prometheus: PrometheusConfig = Field(default_factory=PrometheusConfig)
    snmp: SnmpConfig = Field(default_factory=SnmpConfig)
    myst: MystCollectorConfig = Field(default_factory=MystCollectorConfig)
    mystnodes: MystNodesPortalConfig = Field(default_factory=MystNodesPortalConfig)
    outputs: OutputConfig = Field(default_factory=OutputConfig)
    history: HistoryConfig = Field(default_factory=HistoryConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


def load_config(path: str | os.PathLike[str] | None = None) -> MystMonConfig:
    inline_config = os.getenv("MYSTMON_CONFIG_YAML")
    if inline_config:
        raw_inline: dict[str, Any] = yaml.safe_load(inline_config) or {}
        return MystMonConfig.model_validate(raw_inline)

    config_path = Path(path or os.getenv("MYSTMON_CONFIG", "config.yaml"))
    raw = _load_yaml_file(config_path)
    if raw is None:
        return MystMonConfig()

    local_override = config_path.with_name("config.local.yaml")
    if local_override != config_path:
        raw = _deep_merge_dicts(raw, _load_yaml_file(local_override) or {})
    return MystMonConfig.model_validate(raw)


def _load_yaml_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged
