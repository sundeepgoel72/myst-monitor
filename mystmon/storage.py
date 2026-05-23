from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class Reading:
    source_type: str
    source_name: str
    metric: str
    value: float | str
    labels: dict[str, str] = field(default_factory=dict)
    collected_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_name": self.source_name,
            "metric": self.metric,
            "value": self.value,
            "labels": self.labels,
            "collected_at": self.collected_at.isoformat(),
        }


class ReadingStore:
    def __init__(self) -> None:
        self._readings: list[Reading] = []
        self._lock = Lock()

    def replace_source(self, source_type: str, source_name: str, readings: list[Reading]) -> None:
        with self._lock:
            self._readings = [
                item
                for item in self._readings
                if not (item.source_type == source_type and item.source_name == source_name)
            ]
            self._readings.extend(readings)

    def all(self) -> list[Reading]:
        with self._lock:
            return list(self._readings)

