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
    
    def __init__(self) -> None:
        """Initialize the reading store.
        
        Creates empty storage structures for readings and source indexing.
        """
        self._readings: dict[tuple[str, str], Reading] = {}
        self._by_source_type: dict[str, set[tuple[str, str]]] = {}
        self._by_metric: dict[str, set[tuple[str, str]]] = {}
    
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
        
        return count
