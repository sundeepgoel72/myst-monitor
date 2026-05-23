from __future__ import annotations

import httpx
from prometheus_client.parser import text_string_to_metric_families

from mystmon.config import PrometheusTarget
from mystmon.storage import Reading


async def collect_prometheus(target: PrometheusTarget, timeout_seconds: int) -> list[Reading]:
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.get(str(target.url))
        response.raise_for_status()

    readings: list[Reading] = []
    for family in text_string_to_metric_families(response.text):
        for sample in family.samples:
            sample_labels = {str(key): str(value) for key, value in sample.labels.items()}
            readings.append(
                Reading(
                    source_type="prometheus",
                    source_name=target.name,
                    metric=sample.name,
                    value=float(sample.value),
                    labels=sample_labels,
                )
            )
    return readings

