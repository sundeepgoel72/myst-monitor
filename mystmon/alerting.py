from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, List, Optional, Dict
from enum import Enum

from mystmon.config import MystMonConfig
from mystmon.storage import ReadingStore

LOGGER = logging.getLogger(__name__)


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertState(Enum):
    FIRING = "firing"
    RESOLVED = "resolved"


@dataclass
class Alert:
    id: str
    name: str
    severity: AlertSeverity
    state: AlertState
    summary: str
    description: str
    labels: dict[str, str]
    starts_at: datetime
    ends_at: Optional[datetime] = None
    fingerprint: str = ""
    last_updated: datetime = None


class AlertingRule:
    def __init__(
        self,
        name: str,
        condition: Callable[[Any], bool],
        severity: AlertSeverity,
        summary: str,
        description: str,
        labels: Optional[dict[str, str]] = None
    ):
        self.name = name
        self.condition = condition
        self.severity = severity
        self.summary = summary
        self.description = description
        self.labels = labels or {}


class AlertManager:
    def __init__(self, config: MystMonConfig):
        self.config = config
        self.active_alerts: dict[str, Alert] = {}
        self.alerting_rules: List[AlertingRule] = []
        self._initialize_default_rules()
    
    def _initialize_default_rules(self) -> None:
        """Initialize default alerting rules for common node issues."""
        # Node offline alert
        def node_offline_condition(reading: Any) -> bool:
            if hasattr(reading, 'source_type') and reading.source_type == 'myst':
                if hasattr(reading, 'metric_name') and reading.metric_name == 'running':
                    return reading.value == 0.0
            return False
        
        self.alerting_rules.append(AlertingRule(
            name="node_offline",
            condition=node_offline_condition,
            severity=AlertSeverity.CRITICAL,
            summary="Node is offline",
            description="A Mysterium node is not running",
            labels={"alert_type": "node_offline"}
        ))
        
        # Low quality alert
        def node_low_quality_condition(reading: Any) -> bool:
            if hasattr(reading, 'source_type') and reading.source_type == 'myst':
                if hasattr(reading, 'metric_name') and reading.metric_name == 'quality':
                    return reading.value < 0.5 if reading.value is not None else False
            return False
        
        self.alerting_rules.append(AlertingRule(
            name="node_low_quality",
            condition=node_low_quality_condition,
            severity=AlertSeverity.WARNING,
            summary="Node quality is low",
            description="A Mysterium node has quality score below 0.5",
            labels={"alert_type": "node_low_quality"}
        ))
        
        # High error count alert
        def node_high_errors_condition(reading: Any) -> bool:
            if hasattr(reading, 'source_type') and reading.source_type == 'myst':
                if hasattr(reading, 'metric_name') and reading.metric_name == 'log_error_or_warning':
                    return reading.value > 10 if reading.value is not None else False
            return False
        
        self.alerting_rules.append(AlertingRule(
            name="node_high_errors",
            condition=node_high_errors_condition,
            severity=AlertSeverity.WARNING,
            summary="Node has high error count",
            description="A Mysterium node has more than 10 error or warning logs",
            labels={"alert_type": "node_high_errors"}
        ))
        
        # Low earnings alert
        def node_low_earnings_condition(reading: Any) -> bool:
            if hasattr(reading, 'source_type') and reading.source_type == 'myst':
                if hasattr(reading, 'metric_name') and reading.metric_name == 'earnings_24h':
                    return reading.value < 0.01 if reading.value is not None else False
            return False
        
        self.alerting_rules.append(AlertingRule(
            name="node_low_earnings",
            condition=node_low_earnings_condition,
            severity=AlertSeverity.WARNING,
            summary="Node earnings are low",
            description="A Mysterium node has earned less than 0.01 MYST in the last 24 hours",
            labels={"alert_type": "node_low_earnings"}
        ))
        
        # High restart count alert
        def node_high_restarts_condition(reading: Any) -> bool:
            if hasattr(reading, 'source_type') and reading.source_type == 'myst':
                if hasattr(reading, 'metric_name') and reading.metric_name == 'restart_count':
                    return reading.value > 5 if reading.value is not None else False
            return False
        
        self.alerting_rules.append(AlertingRule(
            name="node_high_restarts",
            condition=node_high_restarts_condition,
            severity=AlertSeverity.WARNING,
            summary="Node has high restart count",
            description="A Mysterium node has restarted more than 5 times",
            labels={"alert_type": "node_high_restarts"}
        ))
    
    def add_rule(self, rule: AlertingRule) -> None:
        """Add a new alerting rule."""
        self.alerting_rules.append(rule)
    
    def evaluate_reading(self, reading: Any) -> List[Alert]:
        """Evaluate a single reading against all alerting rules."""
        alerts = []
        now = datetime.now()
        for rule in self.alerting_rules:
            if rule.condition(reading):
                alert_id = f"{rule.name}_{reading.source_name if hasattr(reading, 'source_name') else 'unknown'}"
                # Check if alert already exists
                if alert_id in self.active_alerts:
                    # Update existing alert
                    alert = self.active_alerts[alert_id]
                    alert.state = AlertState.FIRING
                    alert.last_updated = now
                else:
                    # Create new alert
                    alert = Alert(
                        id=alert_id,
                        name=rule.name,
                        severity=rule.severity,
                        state=AlertState.FIRING,
                        summary=rule.summary,
                        description=rule.description,
                        labels={**rule.labels, "source": reading.source_name if hasattr(reading, 'source_name') else 'unknown'},
                        starts_at=now,
                        last_updated=now
                    )
                    self.active_alerts[alert_id] = alert
                alerts.append(alert)
        return alerts
    
    def evaluate_all_readings(self, store: ReadingStore) -> List[Alert]:
        """Evaluate all current readings against alerting rules."""
        # First, mark all existing alerts as potentially resolved
        now = datetime.now()
        for alert in self.active_alerts.values():
            if alert.state == AlertState.FIRING:
                alert.state = AlertState.RESOLVED
                alert.ends_at = now
        
        # Evaluate all readings
        all_alerts = []
        for reading in store.all():
            alerts = self.evaluate_reading(reading)
            all_alerts.extend(alerts)
        
        # Resolve alerts that are no longer firing
        resolved_alerts = []
        for alert_id, alert in list(self.active_alerts.items()):
            if alert.state == AlertState.RESOLVED and alert.ends_at:
                resolved_alerts.append(alert)
                del self.active_alerts[alert_id]
        
        return all_alerts
    
    def resolve_alert(self, alert_id: str) -> None:
        """Mark an alert as resolved."""
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.state = AlertState.RESOLVED
            alert.ends_at = datetime.now()
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all currently active alerts."""
        return [alert for alert in self.active_alerts.values() if alert.state == AlertState.FIRING]
    
    def get_all_alerts(self) -> List[Alert]:
        """Get all alerts (active and resolved)."""
        return list(self.active_alerts.values())


def create_default_alert_manager(config: MystMonConfig) -> AlertManager:
    """Create an alert manager with default rules."""
    return AlertManager(config)
