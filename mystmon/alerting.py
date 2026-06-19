from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, List, Optional, Dict
from enum import Enum
import hashlib
import json

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
    ACKNOWLEDGED = "acknowledged"
    SUPPRESSED = "suppressed"


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
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    suppressed_until: Optional[datetime] = None
    group_id: Optional[str] = None


class AlertGroup:
    def __init__(self, id: str, name: str, description: str):
        self.id = id
        self.name = name
        self.description = description
        self.alerts: List[Alert] = []
        self.created_at = datetime.now()
        self.last_updated = datetime.now()


class SuppressionRule:
    def __init__(self, name: str, condition: Callable[[Alert], bool], duration: timedelta):
        self.name = name
        self.condition = condition
        self.duration = duration
        self.active_suppressions: Dict[str, datetime] = {}


class AlertTemplate:
    def __init__(self, name: str, summary_template: str, description_template: str, severity: AlertSeverity):
        self.name = name
        self.summary_template = summary_template
        self.description_template = description_template
        self.severity = severity
    
    def render(self, context: Dict[str, Any]) -> tuple[str, str]:
        summary = self.summary_template.format(**context)
        description = self.description_template.format(**context)
        return summary, description


class AlertingRule:
    def __init__(
        self,
        name: str,
        condition: Callable[[Any], bool],
        severity: AlertSeverity,
        summary: str,
        description: str,
        labels: Optional[dict[str, str]] = None,
        group_by: Optional[List[str]] = None,
        template: Optional[AlertTemplate] = None
    ):
        self.name = name
        self.condition = condition
        self.severity = severity
        self.summary = summary
        self.description = description
        self.labels = labels or {}
        self.group_by = group_by or []
        self.template = template


class AlertManager:
    def __init__(self, config: MystMonConfig):
        self.config = config
        self.active_alerts: dict[str, Alert] = {}
        self.alert_history: list[Alert] = []
        self.alerting_rules: List[AlertingRule] = []
        self.alert_groups: Dict[str, AlertGroup] = {}
        self.suppression_rules: List[SuppressionRule] = []
        self.alert_templates: Dict[str, AlertTemplate] = {}
        self._initialize_default_rules()
        self._initialize_default_templates()
    
    def _initialize_default_templates(self) -> None:
        """Initialize default alert templates."""
        self.alert_templates["node_offline"] = AlertTemplate(
            "node_offline",
            "Node {node_name} is offline",
            "The Mysterium node {node_name} at {node_ip} is not running",
            AlertSeverity.CRITICAL
        )
        
        self.alert_templates["node_low_quality"] = AlertTemplate(
            "node_low_quality",
            "Node {node_name} quality is low",
            "The Mysterium node {node_name} has quality score of {quality_score} which is below threshold",
            AlertSeverity.WARNING
        )
        
        self.alert_templates["node_high_errors"] = AlertTemplate(
            "node_high_errors",
            "Node {node_name} has high error count",
            "The Mysterium node {node_name} has {error_count} error or warning logs",
            AlertSeverity.WARNING
        )
    
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
    
    def add_template(self, template: AlertTemplate) -> None:
        """Add a new alert template."""
        self.alert_templates[template.name] = template
    
    def add_suppression_rule(self, rule: SuppressionRule) -> None:
        """Add a new suppression rule."""
        self.suppression_rules.append(rule)
    
    def add_group(self, group: AlertGroup) -> None:
        """Add a new alert group."""
        self.alert_groups[group.id] = group
    
    def _generate_group_id(self, alert: Alert, group_by: List[str]) -> str:
        """Generate a group ID based on alert labels."""
        if not group_by:
            return None
        
        group_values = []
        for key in group_by:
            if key in alert.labels:
                group_values.append(f"{key}:{alert.labels[key]}")
        
        if not group_values:
            return None
        
        return hashlib.md5("_".join(sorted(group_values)).encode()).hexdigest()
    
    def _apply_suppression_rules(self, alert: Alert) -> bool:
        """Apply suppression rules to an alert. Returns True if alert should be suppressed."""
        now = datetime.now()
        for rule in self.suppression_rules:
            # Clean up expired suppressions
            expired = [key for key, until in rule.active_suppressions.items() if until < now]
            for key in expired:
                del rule.active_suppressions[key]
            
            # Check if this alert matches the suppression rule
            if rule.condition(alert):
                # Check if already suppressed
                suppression_key = f"{rule.name}_{alert.id}"
                if suppression_key in rule.active_suppressions:
                    # Extend suppression
                    rule.active_suppressions[suppression_key] = now + rule.duration
                    alert.state = AlertState.SUPPRESSED
                    alert.suppressed_until = now + rule.duration
                    return True
                else:
                    # Start new suppression
                    rule.active_suppressions[suppression_key] = now + rule.duration
                    alert.state = AlertState.SUPPRESSED
                    alert.suppressed_until = now + rule.duration
                    return True
        return False
    
    def evaluate_reading(self, reading: Any) -> List[Alert]:
        """Evaluate a single reading against all alerting rules."""
        alerts = []
        now = datetime.now()
        for rule in self.alerting_rules:
            if rule.condition(reading):
                # Use template if available
                summary = rule.summary
                description = rule.description
                if rule.template and rule.template.name in self.alert_templates:
                    context = {
                        "node_name": getattr(reading, 'source_name', 'unknown'),
                        "node_ip": reading.labels.get('ip', 'unknown') if hasattr(reading, 'labels') else 'unknown',
                        "quality_score": reading.value if hasattr(reading, 'value') else 'unknown',
                        "error_count": reading.value if hasattr(reading, 'value') else 'unknown'
                    }
                    summary, description = self.alert_templates[rule.template.name].render(context)
                
                alert_id = f"{rule.name}_{reading.source_name if hasattr(reading, 'source_name') else 'unknown'}"
                
                # Generate group ID if grouping is configured
                group_id = self._generate_group_id(Alert(
                    id=alert_id,
                    name=rule.name,
                    severity=rule.severity,
                    state=AlertState.FIRING,
                    summary=summary,
                    description=description,
                    labels={**rule.labels, "source": reading.source_name if hasattr(reading, 'source_name') else 'unknown'},
                    starts_at=now,
                    last_updated=now
                ), rule.group_by)
                
                # Check if alert already exists
                if alert_id in self.active_alerts:
                    # Update existing alert
                    alert = self.active_alerts[alert_id]
                    alert.state = AlertState.FIRING
                    alert.last_updated = now
                    alert.group_id = group_id
                else:
                    # Create new alert
                    alert = Alert(
                        id=alert_id,
                        name=rule.name,
                        severity=rule.severity,
                        state=AlertState.FIRING,
                        summary=summary,
                        description=description,
                        labels={**rule.labels, "source": reading.source_name if hasattr(reading, 'source_name') else 'unknown'},
                        starts_at=now,
                        last_updated=now,
                        group_id=group_id
                    )
                    
                    # Apply suppression rules
                    if self._apply_suppression_rules(alert):
                        # Alert is suppressed, don't add to active alerts
                        continue
                    
                    self.active_alerts[alert_id] = alert
                
                # Add to group if applicable
                if group_id and group_id in self.alert_groups:
                    self.alert_groups[group_id].alerts.append(alert)
                    self.alert_groups[group_id].last_updated = now
                elif group_id:
                    # Create new group
                    group = AlertGroup(
                        id=group_id,
                        name=f"Group for {rule.name}",
                        description=f"Alert group for {rule.name} alerts"
                    )
                    group.alerts.append(alert)
                    self.alert_groups[group_id] = group
                
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
                # Move resolved alert to history
                self.alert_history.append(alert)
                resolved_alerts.append(alert)
                del self.active_alerts[alert_id]
        
        return all_alerts
    
    def acknowledge_alert(self, alert_id: str, acknowledged_by: str = "system") -> bool:
        """Acknowledge an alert."""
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.state = AlertState.ACKNOWLEDGED
            alert.acknowledged_at = datetime.now()
            alert.acknowledged_by = acknowledged_by
            return True
        return False
    
    def suppress_alert(self, alert_id: str, duration: timedelta) -> bool:
        """Suppress an alert for a specified duration."""
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.state = AlertState.SUPPRESSED
            alert.suppressed_until = datetime.now() + duration
            return True
        return False
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all currently active alerts."""
        return [alert for alert in self.active_alerts.values() if alert.state == AlertState.FIRING]
    
    def get_all_alerts(self) -> List[Alert]:
        """Get all alerts (active and resolved)."""
        return list(self.active_alerts.values())
    
    def get_alert_history(self, limit: int = 100, offset: int = 0) -> List[Alert]:
        """Get alert history with pagination."""
        # Return the most recent alerts from history with pagination
        start = len(self.alert_history) - offset - limit
        end = len(self.alert_history) - offset
        if start < 0:
            start = 0
        if end > len(self.alert_history):
            end = len(self.alert_history)
        return self.alert_history[start:end] if start < end else []
    
    def get_alert_groups(self) -> Dict[str, AlertGroup]:
        """Get all alert groups."""
        return self.alert_groups
    
    def get_suppressed_alerts(self) -> List[Alert]:
        """Get all suppressed alerts."""
        now = datetime.now()
        suppressed = []
        for alert in self.active_alerts.values():
            if alert.state == AlertState.SUPPRESSED:
                if alert.suppressed_until and alert.suppressed_until > now:
                    suppressed.append(alert)
                else:
                    # Suppression expired, change state back to FIRING
                    alert.state = AlertState.FIRING
                    alert.suppressed_until = None
        return suppressed


def create_default_alert_manager(config: MystMonConfig) -> AlertManager:
    """Create an alert manager with default rules."""
    return AlertManager(config)
