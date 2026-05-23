# MYST Nodes Maintenance Handover Notes

MystMon follows the operating constraints from the maintenance handover:

- It runs on `192.168.1.72` from `/mnt/ssd/codex/mystmon`.
- It performs read-only Docker inspection and log collection.
- It does not unlock identities, alter wallet state, or restart MYST containers.
- It writes `/data/mystmon/latest.json` for debugging and `/data/mystmon/snmp_extend.txt` for existing SNMP-style monitoring.
- It optionally collects read-only TequilAPI metrics from documented MYST API surfaces when a local API port is mapped.
- It uses a 6-hour default polling interval.

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
cd /mnt/ssd/codex/mystmon
cp .env.example .env
vi .env
docker compose pull mystmon
docker compose up -d mystmon
bash ops/install-systemd-timer.sh
./ops/validate-mystmon.sh
```

Cron fallback:

```bash
crontab -l > /tmp/mystmon-cron || true
cat ops/mystmon.cron >> /tmp/mystmon-cron
crontab /tmp/mystmon-cron
```
