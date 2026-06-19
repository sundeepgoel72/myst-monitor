"""CSV export functionality for MystMon.

This module provides functionality to export collected metrics and readings
to CSV format for further analysis and reporting.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from mystmon.storage import Reading
from mystmon.config import MystMonConfig

logger = logging.getLogger(__name__)


def export_readings_to_csv(readings: List[Reading], csv_path: str) -> None:
    """Export a list of readings to a CSV file.
    
    Args:
        readings: List of Reading objects to export
        csv_path: Path to the CSV file to create
    """
    if not readings:
        logger.info("No readings to export to CSV")
        return
    
    # Ensure the directory exists
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Define CSV headers
    headers = ["timestamp", "source_type", "source_name", "metric_name", "value", "labels"]
    
    try:
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            
            for reading in readings:
                row = {
                    "timestamp": reading.timestamp.isoformat(),
                    "source_type": reading.source_type,
                    "source_name": reading.source_name,
                    "metric_name": reading.metric_name,
                    "value": reading.value,
                    "labels": str(reading.labels) if reading.labels else ""
                }
                writer.writerow(row)
        
        logger.info(f"Successfully exported {len(readings)} readings to {csv_path}")
    except Exception as e:
        logger.error(f"Failed to export readings to CSV: {e}")
        raise


def export_alerts_to_csv(alerts: List[Any], csv_path: str) -> None:
    """Export a list of alerts to a CSV file.
    
    Args:
        alerts: List of Alert objects to export
        csv_path: Path to the CSV file to create
    """
    if not alerts:
        logger.info("No alerts to export to CSV")
        return
    
    # Ensure the directory exists
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Define CSV headers for alerts
    headers = [
        "id", "name", "severity", "state", "summary", "description", 
        "starts_at", "ends_at", "last_updated", "acknowledged_at", "acknowledged_by"
    ]
    
    try:
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            
            for alert in alerts:
                # Handle both Alert objects and dict representations
                if hasattr(alert, '__dict__'):
                    alert_dict = alert.__dict__
                else:
                    alert_dict = alert
                
                row = {
                    "id": alert_dict.get('id', ''),
                    "name": alert_dict.get('name', ''),
                    "severity": str(alert_dict.get('severity', '')),
                    "state": str(alert_dict.get('state', '')),
                    "summary": alert_dict.get('summary', ''),
                    "description": alert_dict.get('description', ''),
                    "starts_at": alert_dict.get('starts_at').isoformat() if alert_dict.get('starts_at') else '',
                    "ends_at": alert_dict.get('ends_at').isoformat() if alert_dict.get('ends_at') else '',
                    "last_updated": alert_dict.get('last_updated').isoformat() if alert_dict.get('last_updated') else '',
                    "acknowledged_at": alert_dict.get('acknowledged_at').isoformat() if alert_dict.get('acknowledged_at') else '',
                    "acknowledged_by": alert_dict.get('acknowledged_by', '')
                }
                writer.writerow(row)
        
        logger.info(f"Successfully exported {len(alerts)} alerts to {csv_path}")
    except Exception as e:
        logger.error(f"Failed to export alerts to CSV: {e}")
        raise


def export_snapshot_to_csv(snapshot_data: Dict[str, Any], csv_path: str) -> None:
    """Export snapshot data to a CSV file.
    
    Args:
        snapshot_data: Dictionary containing snapshot data
        csv_path: Path to the CSV file to create
    """
    if not snapshot_data:
        logger.info("No snapshot data to export to CSV")
        return
    
    # Ensure the directory exists
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Export nodes data
        nodes = snapshot_data.get("nodes", [])
        if nodes:
            nodes_csv_path = str(Path(csv_path).with_name(Path(csv_path).stem + "_nodes.csv"))
            with open(nodes_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                # Define headers for nodes
                headers = [
                    "name", "running", "restart_count", "uptime_seconds", 
                    "provider_quality", "earnings_24h", "sessions_active"
                ]
                writer = csv.DictWriter(csvfile, fieldnames=headers)
                writer.writeheader()
                
                for node in nodes:
                    row = {
                        "name": node.get("name", ""),
                        "running": node.get("running", False),
                        "restart_count": node.get("restart_count", 0),
                        "uptime_seconds": node.get("uptime_seconds", 0),
                        "provider_quality": _get_nested_value(node, ["api", "management", "provider", "provider_stats", "quality"]),
                        "earnings_24h": _get_nested_value(node, ["earnings_24h"]),
                        "sessions_active": _get_nested_value(node, ["api", "management", "sessions", "sessions", "count"])
                    }
                    writer.writerow(row)
            
            logger.info(f"Successfully exported {len(nodes)} nodes to {nodes_csv_path}")
        
        # Export portal data if available
        mystnodes = snapshot_data.get("mystnodes", {})
        if mystnodes:
            portal_csv_path = str(Path(csv_path).with_name(Path(csv_path).stem + "_portal.csv"))
            with open(portal_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                headers = ["metric", "value"]
                writer = csv.DictWriter(csvfile, fieldnames=headers)
                writer.writeheader()
                
                # Export portal summary metrics
                endpoints = mystnodes.get("endpoints", {})
                me_data = _get_nested_value(endpoints, ["me", "data"]) or {}
                nodes_info = _get_nested_value(me_data, ["nodesInfo"]) or {}
                
                summary_metrics = {
                    "nodes_total": nodes_info.get("totalCount", 0),
                    "nodes_online": nodes_info.get("onlineCount", 0),
                    "earnings_total": _get_nested_value(endpoints, ["total_earnings", "data", "earningsTotal"], 0),
                    "transferred_total": _get_nested_value(endpoints, ["total_transferred", "data", "transferredTotal"], 0)
                }
                
                for metric, value in summary_metrics.items():
                    writer.writerow({"metric": metric, "value": value})
            
            logger.info(f"Successfully exported portal data to {portal_csv_path}")
            
    except Exception as e:
        logger.error(f"Failed to export snapshot to CSV: {e}")
        raise


def _get_nested_value(data: Dict[str, Any], path: List[str], default=None) -> Any:
    """Get a nested value from a dictionary using a path.
    
    Args:
        data: Dictionary to search in
        path: List of keys representing the path
        default: Default value to return if path not found
        
    Returns:
        The value at the nested path or default
    """
    current = data
    for key in path:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def generate_csv_reports(config: MystMonConfig, store: Any, alert_manager: Any = None) -> None:
    """Generate all configured CSV reports.
    
    Args:
        config: MystMon configuration
        store: ReadingStore instance
        alert_manager: AlertManager instance (optional)
    """
    try:
        # Export all readings
        all_readings = list(store.all()) if store else []
        if all_readings:
            export_readings_to_csv(all_readings, config.outputs.csv_export_path)
        
        # Export alerts if alert manager is available
        if alert_manager:
            active_alerts = alert_manager.get_active_alerts()
            if active_alerts:
                alerts_csv_path = str(Path(config.outputs.csv_export_path).with_name("alerts.csv"))
                export_alerts_to_csv(active_alerts, alerts_csv_path)
        
        # Export snapshot data if available
        snapshot_path = Path(config.outputs.latest_json_path)
        if snapshot_path.exists():
            try:
                import json
                content = snapshot_path.read_text(encoding="utf-8")
                if content.strip():
                    snapshot_data = json.loads(content)
                    snapshot_csv_path = str(Path(config.outputs.csv_export_path).with_name("snapshot.csv"))
                    export_snapshot_to_csv(snapshot_data, snapshot_csv_path)
            except Exception as e:
                logger.warning(f"Failed to export snapshot to CSV: {e}")
        
        logger.info("CSV report generation completed successfully")
    except Exception as e:
        logger.error(f"Failed to generate CSV reports: {e}")
        raise
