# MystMon API

MystMon exposes a small API for health checks, configuration visibility, manual collection, latest snapshots, SQLite-backed history, Prometheus scraping, and the browser UI.

Base URL in the default Docker install:

```text
http://localhost:8072
```

Web UI base path:

```text
http://localhost:8072/ui
```

`GET /` redirects to `/ui/`.

## `GET /health`

Returns service status and version.

```json
{
  "status": "ok",
  "version": "0.11"
}
```

## UI Routes

- `GET /ui` - simplified Home screen
- `GET /ui/fleet` - fleet page
- `GET /ui/history` - history page
- `GET /ui/settings` - settings page
- `GET /ui/node/{node_key}` - node history page

The UI should populate monitoring information from SQLite-backed history, not directly from snapshot files.

## `GET /api/v1/config`

Returns the active configuration after defaults and validation have been applied.

## `GET /api/v1/readings`

Returns generic readings held in memory from optional Prometheus/SNMP polling.

## `GET /api/v1/snapshot`

Returns the latest JSON snapshot file. This remains useful for debugging and exports, but it is not the preferred source for UI rendering.

## `POST /api/v1/collect`

Runs an immediate collection pass for enabled collectors.

## `GET /api/v1/history/latest`

Returns the latest persisted collection metadata from SQLite.

## `GET /api/v1/history/overall?limit=100`

Returns recent SQLite-backed collection records with fleet summary values for each run.

## `GET /api/v1/history/delta?hours=24`

Returns fleet and per-node changes between the latest collection and the nearest collection at or before the requested lookback window.

## `GET /api/v1/history/nodes`

Returns the latest SQLite-backed per-node metrics. Use `latest_only=false&limit=100&offset=0` for raw recent node rows across collection runs.

## `GET /api/v1/history/nodes/{node}?limit=100&offset=0&hours=24`

Returns SQLite-backed history for one node. `{node}` may be the node key, identity, exact node name, container name, or part of the node name.

Use `hours` for preset range filtering in the UI such as `24`, `168`, and `720`.

## `GET /metrics`

Returns the latest numeric readings in Prometheus text format.

## UI Support Endpoints

The browser UI also consumes these internal endpoints:

- `GET /api/v1/ui/config`
- `GET /api/v1/ui/home`
- `GET /api/v1/collectors/status`
- `GET /api/v1/system/info`
- `GET /api/v1/history/export?format=json|csv&hours=24`
