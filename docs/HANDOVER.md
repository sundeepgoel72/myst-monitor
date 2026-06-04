# MYST Nodes Maintenance Handover Notes

MystMon follows the operating constraints from the maintenance handover:

- It runs from the repository root on `192.168.1.72`.
- It performs read-only Docker inspection and log collection.
- It does not unlock identities, alter wallet state, or restart MYST containers.
- It writes `data/latest.json` for debugging and `data/snmp_extend.txt` for existing SNMP-style monitoring.
- It optionally collects read-only TequilAPI metrics from documented MYST API surfaces when a local API port is mapped.
- It uses a 6-hour default polling interval.
- The current release is `v0.73.0`, and the prod container is running `localhost:5050/mystmon:0.73`.

Known hosts from the handover:

| Host | Role | Notes |
| --- | --- | --- |
| `192.168.1.72` | HP400 / main management host | Main Docker and monitoring host. |
| `192.168.1.173` | Tower / VLAN13 | Previously had MYST metrics signing auth/unlock warning. |
| `192.168.1.174` | VLAN14 node | Intermittent SSH reachability. |
| `192.168.1.175` | RPi AI / VLAN15 | Also runs Hailo/Frigate helpers. |
| `192.168.1.176` | RPi Touch / VLAN16 | Expected port range `56000-56999`. |

Useful install commands on `.72`:

```bash
cd /mnt/ssd/projects/mystmon
cp .env.example .env
vi .env
docker compose pull mystmon
docker compose up -d mystmon
bash ops/install-systemd-timer.sh
./ops/validate-mystmon.sh
```

Release coordination:

- Issue tracking: [#1](https://github.com/sundeepgoel72/myst-monitor/issues/1)
- Release tag: `v0.73.0`
- Publish image tag: `localhost:5050/mystmon:0.73`

For local development, use `docker compose -f docker-compose.dev.yml up` so the service is built from the checkout instead of the published image. For deployment, use the default `docker-compose.yml`.

If the host is still on a legacy checkout path, run the migration checklist first:

- [PATH_MIGRATION.md](PATH_MIGRATION.md)

Cron fallback:

```bash
crontab -l > /tmp/mystmon-cron || true
cat ops/mystmon.cron >> /tmp/mystmon-cron
crontab /tmp/mystmon-cron
```
