from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


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
    tequilapi_port: int | None = None
    enabled: bool = True


class MystNodesConfig(BaseModel):
    base_url: str = "https://my.mystnodes.com"


class TequilApiEndpointConfig(BaseModel):
    name: str
    path: str
    metric_prefix: str
    category: str = "general"
    method: str = "GET"

    @field_validator("method")
    @classmethod
    def only_get(cls, value: str) -> str:
        method = value.upper()
        if method != "GET":
            raise ValueError("TequilAPI endpoints must use GET")
        return method

    @field_validator("path")
    @classmethod
    def normalize_path(cls, value: str) -> str:
        path = value.strip()
        if not path.startswith("/"):
            path = f"/{path}"
        return path

    @model_validator(mode="after")
    def forbid_risky_paths(self) -> "TequilApiEndpointConfig":
        path = self.path.split("?", 1)[0]
        allowed_paths = {
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
            "/location",
            "/connection/location",
            "/connection/proxy/location",
            "/nat/type",
        }
        if path in allowed_paths:
            return self

        risky_prefixes = (
            "/auth/",
            "/stop",
            "/feedback/",
            "/connection/",
            "/connection",
            "/config/user",
            "/config/set",
            "/identities/create",
            "/identities/import",
            "/identities/register",
            "/services/",
            "/services",
            "/transactor/settle/",
            "/transactor/staking",
            "/transactor/rewards",
            "/transactor/payments",
        )
        if path in {"/stop", "/connection"}:
            raise ValueError("risky TequilAPI endpoint is not allowed")
        if any(path.startswith(prefix) for prefix in risky_prefixes):
            allowed_location_paths = {"/connection/location", "/connection/proxy/location", "/location", "/nat/type"}
            if path not in allowed_location_paths:
                raise ValueError("risky TequilAPI endpoint is not allowed")
        return self


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
            TequilApiEndpointConfig(name="healthcheck", path="/healthcheck", metric_prefix="health", category="health"),
            TequilApiEndpointConfig(name="identities", path="/identities", metric_prefix="identities", category="identities"),
            TequilApiEndpointConfig(name="services", path="/services", metric_prefix="services", category="services"),
            TequilApiEndpointConfig(name="sessions", path="/sessions", metric_prefix="sessions", category="sessions"),
            TequilApiEndpointConfig(name="sessions_connectivity_status", path="/sessions-connectivity-status", metric_prefix="sessions", category="sessions"),
            TequilApiEndpointConfig(name="session_stats_dailies", path="/sessions/stats-daily", metric_prefix="sessions", category="sessions"),
            TequilApiEndpointConfig(name="session_stats_aggregated", path="/sessions/stats-aggregated", metric_prefix="sessions", category="sessions"),
            TequilApiEndpointConfig(name="provider_activity_stats", path="/node/provider/activity-stats", metric_prefix="provider", category="provider"),
            TequilApiEndpointConfig(name="provider_quality", path="/node/provider/quality", metric_prefix="provider", category="provider"),
            TequilApiEndpointConfig(name="provider_service_earnings", path="/node/provider/service-earnings", metric_prefix="provider", category="provider"),
            TequilApiEndpointConfig(name="provider_sessions", path="/node/provider/sessions", metric_prefix="provider", category="provider"),
            TequilApiEndpointConfig(name="provider_sessions_1d", path="/node/provider/sessions-count?range=1d", metric_prefix="provider_sessions_1d", category="provider"),
            TequilApiEndpointConfig(name="provider_sessions_7d", path="/node/provider/sessions-count?range=7d", metric_prefix="provider_sessions_7d", category="provider"),
            TequilApiEndpointConfig(name="provider_transferred_data", path="/node/provider/transferred-data", metric_prefix="provider", category="provider"),
            TequilApiEndpointConfig(name="payments_balance", path="/transactor/fees", metric_prefix="payments", category="payments"),
            TequilApiEndpointConfig(name="payments_balance_v2", path="/v2/transactor/fees", metric_prefix="payments", category="payments"),
            TequilApiEndpointConfig(name="settlement_history", path="/settle/history", metric_prefix="settlements", category="settlements"),
            TequilApiEndpointConfig(name="config", path="/config", metric_prefix="config", category="config"),
            TequilApiEndpointConfig(name="config_default", path="/config/default", metric_prefix="config", category="config"),
            TequilApiEndpointConfig(name="location", path="/location", metric_prefix="location", category="location"),
            TequilApiEndpointConfig(name="connection_location", path="/connection/location", metric_prefix="location", category="location"),
            TequilApiEndpointConfig(name="connection_proxy_location", path="/connection/proxy/location", metric_prefix="location", category="location"),
            TequilApiEndpointConfig(name="nat_type", path="/nat/type", metric_prefix="nat", category="nat"),
        ]
    )
    containers: list[MystContainerConfig] = Field(default_factory=list)
    remote_hosts: list[MystRemoteHostConfig] = Field(default_factory=list)


class SystemConfig(BaseModel):
    enabled: bool = True
    collect_interval_seconds: int = Field(default=60, ge=10)


class MystNodesPortalEndpointConfig(BaseModel):
    name: str
    method: str = "GET"
    path: str
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)


class MystNodesPortalAccountConfig(BaseModel):
    """Configuration for a single MystNodes portal account."""
    account: str = "default"
    enabled: bool = True
    base_url: str | None = None
    password: str | None = None
    password_env: str | None = None
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
    csv_export_path: str = "/data/mystmon/csv"


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


class UIConfig(BaseModel):
    enabled: bool = True
    path: str = "/ui"
    auto_refresh_interval_seconds: int = Field(default=30, ge=5)
    max_history_points: int = Field(default=500, ge=50, le=5000)
    theme: str = Field(default="system", pattern="^(light|dark|system)$")
    enable_advanced_filtering: bool = True


class AlertingConfig(BaseModel):
    enabled: bool = True
    evaluation_interval_seconds: int = Field(default=60, ge=10)
    notification_cooldown_seconds: int = Field(default=3600, ge=60)  # 1 hour


class MystMonConfig(BaseModel):
    service: ServiceConfig = Field(default_factory=ServiceConfig)
    prometheus: PrometheusConfig = Field(default_factory=PrometheusConfig)
    snmp: SnmpConfig = Field(default_factory=SnmpConfig)
    myst: MystCollectorConfig = Field(default_factory=MystCollectorConfig)
    mystnodes: MystNodesConfig = Field(default_factory=MystNodesConfig)
    mystnodes_accounts: list[MystNodesPortalAccountConfig] = Field(default_factory=list)
    system: SystemConfig = Field(default_factory=SystemConfig)
    outputs: OutputConfig = Field(default_factory=OutputConfig)
    history: HistoryStore = Field(default_factory=HistoryConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    alerting: AlertingConfig = Field(default_factory=AlertingConfig)


def _validate_required_config(config: MystMonConfig) -> None:
    """Validate required configuration values that can't be expressed in the model."""
    for account in config.mystnodes_accounts:
        if account.enabled:
            if not account.wallet_address:
                raise ValueError(f"wallet_address is required for MystNodes account {account.account}")
            if not account.base_url:
                account.base_url = config.mystnodes.base_url
            if not account.account:
                raise ValueError("account is required for MystNodes accounts")
            if not account.password and not account.password_env:
                raise ValueError(f"password or password_env is required for MystNodes account {account.account}")


def load_config(path: str | os.PathLike[str] | None = None) -> MystMonConfig:
    inline_config = os.getenv("MYSTMON_CONFIG_YAML")
    if inline_config:
        raw_inline: dict[str, Any] = yaml.safe_load(inline_config) or {}
        config = MystMonConfig.model_validate(raw_inline)
        _validate_required_config(config)
        return config

    config_path = Path(path or os.getenv("MYSTMON_CONFIG", "config.yaml"))
    raw = _load_yaml_file(config_path)
    if raw is None:
        return MystMonConfig()

    local_override = config_path.with_name("config.local.yaml")
    if local_override != config_path:
        raw = _deep_merge_dicts(raw, _load_yaml_file(local_override) or {})
    config = MystMonConfig.model_validate(raw)
    _validate_required_config(config)
    return config


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
