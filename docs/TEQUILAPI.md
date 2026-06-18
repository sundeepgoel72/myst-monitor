# TequilAPI Integration in MystMon

MystMon implements a comprehensive read-only integration with the Mysterium Node TequilAPI to provide detailed monitoring and management insights for your nodes.

## Overview

TequilAPI is the REST API exposed by Mysterium Nodes that provides programmatic access to node operations. By default, it's available on port `4050` and uses HTTP Basic Authentication.

MystMon implements a **read-only first** approach to TequilAPI integration, ensuring that no node state is changed, no identities are unlocked, and no configuration is modified during monitoring.

## Safety Policy

MystMon enforces a strict safety policy for TequilAPI interactions:

### Allowed Operations
- Only `GET` requests are made to TequilAPI endpoints
- Configured endpoint query strings are preserved on fetch, while safety and schema matching compare only the path component
- All data is collected for monitoring purposes only

### Blocked Operations
MystMon explicitly blocks any interaction with these sensitive endpoints:
- Connection management: `/connection`, `/stop`
- Identity operations: `/identities/import`, `/identities/create`, `/identities/{id}/unlock`, `/identities/register`
- Configuration changes: `/config/set`
- Settlement operations: `/settle/withdraw`, `/settle/pay`
- Authentication: `/auth/login`, `/auth/logout`
- Feedback submission: `/feedback`, `/bug-report`

### Data Redaction
Sensitive information is aggressively redacted:
- Authentication credentials are never stored or logged
- Private keys, wallet secrets, and other sensitive data are filtered out
- Email addresses and full payment identifiers are not stored
- Raw configuration secrets are redacted before storage

## Endpoint Discovery

MystMon automatically discovers supported endpoints by fetching `/docs/swagger.json` first and falling back to `/openapi.json` from each node's TequilAPI. This allows MystMon to:
- Identify which endpoints are actually supported by each node
- Skip configured endpoints that aren't available
- Adapt to different node versions and configurations

## Supported Categories

MystMon collects data from these TequilAPI categories:

### Health
- `/healthcheck` - Node health status and uptime information

### Identities
- `/identities` - Node identity information

### Services
- `/services` - Running services status

### Sessions
- `/sessions` - Active sessions
- `/sessions-connectivity-status` - Session connectivity state
- `/sessions/stats-daily` - Daily session statistics
- `/sessions/stats-aggregated` - Aggregated session statistics

### Provider Statistics
- `/node/provider/activity-stats` - Provider activity metrics
- `/node/provider/quality` - Provider quality
- `/node/provider/service-earnings` - Service earnings summary
- `/node/provider/sessions` - Provider session details
- `/node/provider/sessions-count?range=1d` - Daily session counts
- `/node/provider/sessions-count?range=7d` - Weekly session counts
- `/node/provider/transferred-data` - Provider transferred data

### Payments & Settlements
- `/transactor/fees` - Current fee summary
- `/v2/transactor/fees` - Current fee summary, v2
- `/settle/history` - Settlement history
- `/transactor/chains-summary` - Chain summary
- `/transactor/fees` - Transaction fee summary

### Configuration
- `/config` - Node configuration summary
- `/config/default` - Default configuration summary

### Location & NAT
- `/location` - Node location information
- `/connection/location` - Connection location information
- `/connection/proxy/location` - Proxy connection location information
- `/nat/type` - NAT type detection

## Configuration

### LAN Exposure Assumptions
MystMon assumes TequilAPI is exposed on the local network:
- Default port: `4050`
- Per-node hosts configured in `myst.containers`
- Remote host TequilAPI ports configured in `remote_hosts[].tequilapi_port`

### Authentication
Basic Authentication is supported:
- Username configured with `api_username`
- Password configured via environment variable `api_password_env`

Example:
```yaml
myst:
  api_username: "myst"
  api_password_env: "MYSTMON_TEQUILAPI_PASSWORD"
```

Then set the environment variable:
```bash
export MYSTMON_TEQUILAPI_PASSWORD="your_password"
```

## Data Structure

Collected TequilAPI data is organized in the node snapshot under the `api` key:

```json
{
  "api": {
    "enabled": true,
    "base_url": "http://192.168.1.72:4050",
    "up": true,
    "auth": true,
    "schema_available": true,
    "last_check": "2026-05-23T12:00:00Z",
    "endpoints": {
      "healthcheck": {
        "ok": true,
        "status_code": 200,
        "reason": null,
        "supported": true,
        "category": "health",
        "last_check": "2026-05-23T12:00:00Z"
      }
    },
    "metrics": {
      "health_uptime_seconds": 35010,
      "identities_count": 1
    },
    "labels": {
      "health_version": "1.35.4"
    },
    "management": {
      "health": {
        "healthcheck": { "uptime": "10h30m10s", "version": "1.35.4" }
      },
      "sessions": {
        "sessions": { "count": 5 }
      }
    }
  }
}
```

Snapshot data is stored read-only. The collector redacts identity, payment, settlement, and address-like fields before logging or persistence. Raw endpoint responses are normalized into management summaries so the UI does not need to scrape endpoint blobs directly.

## Prometheus Metrics

TequilAPI data is exported as Prometheus metrics:
- `mystmon_node_api_up` - Overall API availability
- `mystmon_node_api_auth` - Authentication status
- `mystmon_node_api_schema_available` - Schema discovery success
- `mystmon_node_api_endpoint_up` - Per-endpoint status
- `mystmon_node_api_metric` - Numeric metrics from endpoints
- `mystmon_node_api_info` - String metadata as info metrics
- Category-specific metrics for sessions, provider quality, payments, and NAT type

This implementation provides comprehensive read-only monitoring of Mysterium nodes while maintaining strict security boundaries.
