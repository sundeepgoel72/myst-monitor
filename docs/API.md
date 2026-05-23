# MystMon API

MystMon exposes a small API for health checks, configuration visibility, manual collection, latest MYST node snapshots, and Prometheus scraping.

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

Returns generic readings held in memory from optional Prometheus/SNMP polling.

## `GET /api/v1/snapshot`

Returns the latest MYST container snapshot. If no snapshot exists yet, MystMon runs a collection pass first.

```json
{
  "generated_at": "2026-05-23T12:00:00+00:00",
  "collection_counts": {
    "myst": 4,
    "prometheus": 0,
    "snmp": 0
  },
  "nodes": [
    {
      "name": "myst.16.x",
      "running": true,
      "restart_count": 0,
      "uptime_seconds": 12345,
      "log_counts": {
        "error_or_warning": 0,
        "promise": 4,
        "session": 2,
        "identity_warning": 0
      },
      "api": {
        "up": true,
        "metrics": {
          "health_uptime_seconds": 35010,
          "identities_count": 1,
          "services_running_count": 1
        },
        "labels": {
          "health_version": "1.35.4"
        }
      }
    }
  ]
}
```

## `POST /api/v1/collect`

Runs an immediate collection pass for enabled Prometheus and SNMP targets.

```json
{
  "myst": 4,
  "prometheus": 42,
  "snmp": 0
}
```

## `GET /metrics`

Returns the latest numeric readings in Prometheus text format.

```text
# HELP mystmon_node_running MYST container running state.
# TYPE mystmon_node_running gauge
mystmon_node_running{node="myst.16.x"} 1.0
mystmon_node_api_metric{metric="health_uptime_seconds",node="myst.16.x"} 35010.0
```

## OpenAPI

Interactive docs are available at `/docs`. The OpenAPI schema is available at `/openapi.json`.
