# MystMon API

MystMon exposes a small API for health checks, configuration visibility, manual collection, and Prometheus scraping.

Base URL in the default Docker install:

```text
http://localhost:8072
```

## `GET /health`

Returns service status and version.

```json
{
  "status": "ok",
  "version": "0.72.0"
}
```

## `GET /api/v1/config`

Returns the active configuration after defaults and validation have been applied.

## `GET /api/v1/readings`

Returns the latest readings held in memory.

```json
[
  {
    "source_type": "snmp",
    "source_name": "existing-snmp-framework",
    "metric": "sys_uptime",
    "value": 123456,
    "labels": {
      "host": "192.168.1.72",
      "oid": "1.3.6.1.2.1.1.3.0"
    },
    "collected_at": "2026-05-23T12:00:00+00:00"
  }
]
```

## `POST /api/v1/collect`

Runs an immediate collection pass for enabled Prometheus and SNMP targets.

```json
{
  "prometheus": 42,
  "snmp": 2
}
```

## `GET /metrics`

Returns the latest numeric readings in Prometheus text format.

```text
# HELP mystmon_reading Latest numeric reading collected by MystMon.
# TYPE mystmon_reading gauge
mystmon_reading{metric="sys_uptime",source_name="existing-snmp-framework",source_type="snmp"} 123456.0
```

## OpenAPI

Interactive docs are available at `/docs`. The OpenAPI schema is available at `/openapi.json`.

