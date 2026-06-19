"""Storage for collected readings and metrics.

This module provides in-memory storage for metric readings collected from
various sources including Docker containers, Prometheus endpoints, SNMP targets,
and Mysterium node TequilAPI endpoints.

The storage is organized by source type and name, allowing efficient retrieval
and replacement of readings for specific sources during collection cycles.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Iterator, List, Optional, Callable
from dataclasses import dataclass
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Reading:
    """A single metric reading from a data source.
    
    Represents a single measurement or data point collected from a source.
    Each reading includes metadata about the source, the metric name, value,
    labels, timestamp, and optional raw data.
    """
    source_type: str
    source_name: str
    metric_name: str
    value: float
    labels: dict[str, str]
    timestamp: datetime
    raw_data: Any = None
    
    def as_dict(self) -> dict[str, Any]:
        """Convert reading to dictionary representation.
        
        Returns:
            Dictionary representation of the reading suitable for serialization
        """
        return {
            "source_type": self.source_type,
            "source_name": self.source_name,
            "metric_name": self.metric_name,
            "value": self.value,
            "labels": self.labels,
            "timestamp": self.timestamp.isoformat(),
            "raw_data": self.raw_data,
        }


class ReadingStore:
    """In-memory storage for collected readings.
    
    Provides efficient storage and retrieval of metric readings organized
    by source type and name. Supports replacing all readings for a source
    and clearing old readings based on age.
    """
    
    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize the reading store.
        
        Creates empty storage structures for readings and source indexing.
        If db_path is provided, also initializes persistent storage.
        """
        self._readings: dict[tuple[str, str], Reading] = {}
        self._by_source_type: dict[str, set[tuple[str, str]]] = {}
        self._by_metric: dict[str, set[tuple[str, str]]] = {}
        self.db_path = db_path
        if db_path:
            self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the SQLite database for persistent storage."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables for readings and alerts
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_name TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                value REAL NOT NULL,
                labels TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                raw_data TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                severity TEXT NOT NULL,
                state TEXT NOT NULL,
                summary TEXT NOT NULL,
                description TEXT NOT NULL,
                labels TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                ends_at TEXT,
                fingerprint TEXT,
                last_updated TEXT,
                acknowledged_at TEXT,
                acknowledged_by TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add(self, reading: Reading) -> None:
        """Add a reading to the store.
        
        Args:
            reading: The reading to add to storage
        """
        key = (reading.source_type, reading.source_name)
        self._readings[key] = reading
        
        # Update source type index
        if reading.source_type not in self._by_source_type:
            self._by_source_type[reading.source_type] = set()
        self._by_source_type[reading.source_type].add(key)
        
        # Update metric index
        if reading.metric_name not in self._by_metric:
            self._by_metric[reading.metric_name] = set()
        self._by_metric[reading.metric_name].add(key)
        
        # Persist to database if enabled
        if self.db_path:
            self._persist_reading(reading)
    
    def _persist_reading(self, reading: Reading) -> None:
        """Persist a reading to the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO readings 
                (source_type, source_name, metric_name, value, labels, timestamp, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                reading.source_type,
                reading.source_name,
                reading.metric_name,
                reading.value,
                str(reading.labels),
                reading.timestamp.isoformat(),
                str(reading.raw_data) if reading.raw_data else None
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to persist reading: {e}")
    
    def replace_source(self, source_type: str, source_name: str, readings: List[Reading]) -> None:
        """Replace all readings for a given source.
        
        Removes all existing readings for the specified source and adds
        the new readings in their place.
        
        Args:
            source_type: Type of the source (e.g., 'myst', 'prometheus')
            source_name: Name of the source
            readings: List of readings to replace with
        """
        # Remove existing readings for this source
        if source_type in self._by_source_type:
            keys_to_remove = {
                key for key in self._by_source_type[source_type] 
                if key[1] == source_name
            }
            for key in keys_to_remove:
                # Remove from metric index
                reading = self._readings.get(key)
                if reading and reading.metric_name in self._by_metric:
                    self._by_metric[reading.metric_name].discard(key)
                
                del self._readings[key]
                self._by_source_type[source_type].discard(key)
        
        # Add new readings
        for reading in readings:
            self.add(reading)
    
    def get(self, source_type: str, source_name: str) -> Reading | None:
        """Get a reading by source type and name.
        
        Args:
            source_type: Type of the source
            source_name: Name of the source
            
        Returns:
            The reading or None if not found
        """
        key = (source_type, source_name)
        return self._readings.get(key)
    
    def all(self) -> Iterator[Reading]:
        """Get all readings.
        
        Returns:
            Iterator over all readings in the store
        """
        return iter(self._readings.values())
    
    def by_source_type(self, source_type: str) -> Iterator[Reading]:
        """Get all readings for a given source type.
        
        Args:
            source_type: Type of the source
            
        Returns:
            Iterator over readings for the source type
        """
        if source_type not in self._by_source_type:
            return
        for key in self._by_source_type[source_type]:
            yield self._readings[key]
    
    def by_metric(self, metric_name: str) -> Iterator[Reading]:
        """Get all readings for a given metric.
        
        Args:
            metric_name: Name of the metric
            
        Returns:
            Iterator over readings for the metric
        """
        if metric_name not in self._by_metric:
            return
        for key in self._by_metric[metric_name]:
            reading = self._readings.get(key)
            if reading:
                yield reading
    
    def filter(self, predicate: Callable[[Reading], bool]) -> List[Reading]:
        """Filter readings by a predicate function.
        
        Args:
            predicate: Function that takes a Reading and returns True/False
            
        Returns:
            List of readings that match the predicate
        """
        return [reading for reading in self._readings.values() if predicate(reading)]
    
    def clear_old(self, max_age: timedelta) -> int:
        """Clear readings older than max_age.
        
        Removes all readings that are older than the specified maximum age.
        
        Args:
            max_age: Maximum age for readings
            
        Returns:
            Number of readings removed
        """
        cutoff = datetime.now() - max_age
        old_keys = [
            key for key, reading in self._readings.items()
            if reading.timestamp < cutoff
        ]
        
        count = len(old_keys)
        for key in old_keys:
            reading = self._readings[key]
            # Remove from indices
            if reading.source_type in self._by_source_type:
                self._by_source_type[reading.source_type].discard(key)
            if reading.metric_name in self._by_metric:
                self._by_metric[reading.metric_name].discard(key)
            del self._readings[key]
        
        # Also remove from database if enabled
        if self.db_path:
            self._clear_old_from_db(cutoff)
        
        return count
    
    def _clear_old_from_db(self, cutoff: datetime) -> None:
        """Clear old readings from the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM readings WHERE timestamp < ?', (cutoff.isoformat(),))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to clear old readings from database: {e}")
    
    def persist_alert(self, alert: Any) -> None:
        """Persist an alert to the database."""
        if not self.db_path:
            return
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO alerts 
                (id, name, severity, state, summary, description, labels, starts_at, ends_at, 
                 fingerprint, last_updated, acknowledged_at, acknowledged_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                alert.id,
                alert.name,
                alert.severity.value if hasattr(alert.severity, 'value') else str(alert.severity),
                alert.state.value if hasattr(alert.state, 'value') else str(alert.state),
                alert.summary,
                alert.description,
                str(alert.labels),
                alert.starts_at.isoformat() if alert.starts_at else None,
                alert.ends_at.isoformat() if alert.ends_at else None,
                alert.fingerprint,
                alert.last_updated.isoformat() if alert.last_updated else None,
                alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                alert.acknowledged_by
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to persist alert: {e}")
    
    def get_alert_history(self, limit: int = 100) -> List[Any]:
        """Get alert history from the database."""
        if not self.db_path:
            return []
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, name, severity, state, summary, description, labels, starts_at, ends_at,
                       fingerprint, last_updated, acknowledged_at, acknowledged_by
                FROM alerts
                ORDER BY last_updated DESC
                LIMIT ?
            ''', (limit,))
            
            alerts = []
            for row in cursor.fetchall():
                # This is a simplified reconstruction of Alert objects
                # In a real implementation, you might want to store more structured data
                alert_data = {
                    'id': row[0],
                    'name': row[1],
                    'severity': row[2],
                    'state': row[3],
                    'summary': row[4],
                    'description': row[5],
                    'labels': eval(row[6]) if row[6] else {},
                    'starts_at': datetime.fromisoformat(row[7]) if row[7] else None,
                    'ends_at': datetime.fromisoformat(row[8]) if row[8] else None,
                    'fingerprint': row[9],
                    'last_updated': datetime.fromisoformat(row[10]) if row[10] else None,
                    'acknowledged_at': datetime.fromisoformat(row[11]) if row[11] else None,
                    'acknowledged_by': row[12]
                }
                alerts.append(alert_data)
            
            conn.close()
            return alerts
        except Exception as e:
            logger.error(f"Failed to get alert history: {e}")
            return []
