from __future__ import annotations

import logging

import httpx
from prometheus_client.parser import text_string_to_metric_families

from mystmon.config import PrometheusTarget
from mystmon.storage import Reading

LOGGER = logging.getLogger(__name__)


async def collect_prometheus(target: PrometheusTarget, timeout_seconds: int) -> list[Reading]:
    url = str(target.url)
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        LOGGER.exception("Prometheus collection failed target=%s url=%s reason=http_error error=%s", target.name, url, exc)
        raise

    readings: list[Reading] = []
    try:
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
    except Exception as exc:
        LOGGER.warning("Prometheus collection skipped target=%s url=%s reason=parse_error error=%s", target.name, url, exc)
        return []
    return readings
