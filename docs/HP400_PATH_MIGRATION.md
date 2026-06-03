# MystMon HP400 Path Migration

This checklist migrates MystMon on host `192.168.1.72` from the old path:

```text
/mnt/ssd/codex/mystmon
```

to the current project path:

```text
/mnt/ssd/projects/mystmon
```

Use this only if the host is still running MystMon from the old location.

## Goal

- move the runtime tree to `/mnt/ssd/projects/mystmon`
- update the service/timer/cron path assumptions
- preserve `.env`, generated outputs, and current runtime behavior

## Pre-Checks

On `192.168.1.72`:

```bash
sudo systemctl --no-pager --full status mystmon.service mystmon.timer || true
crontab -l | grep mystmon || true
test -d /mnt/ssd/codex/mystmon && echo "old path exists"
test -d /mnt/ssd/projects/mystmon && echo "new path exists"
```

Record:

- whether MystMon is running via systemd timer, cron, or manual Docker commands
- whether `/mnt/ssd/projects/mystmon` already exists
- whether the old path has the authoritative `.env` and generated `data/`

## Recommended Migration

1. Stop scheduled execution.

```bash
sudo systemctl stop mystmon.timer mystmon.service || true
sudo systemctl disable mystmon.timer || true
```

2. If cron is in use, remove or comment out the old MystMon cron entry before continuing.

3. Create the new parent directory if needed.

```bash
mkdir -p /mnt/ssd/projects
```

4. Move the existing runtime tree if the old path is still the source of truth.

```bash
mv /mnt/ssd/codex/mystmon /mnt/ssd/projects/mystmon
```

5. If the new path already contains the code but the old path has the live `.env` or `data/`, merge carefully instead of replacing blindly.

Minimum files to preserve:

- `/mnt/ssd/projects/mystmon/.env`
- `/mnt/ssd/projects/mystmon/config.yaml` if locally customized
- `/mnt/ssd/projects/mystmon/data/latest.json`
- `/mnt/ssd/projects/mystmon/data/snmp_extend.txt`

6. Reinstall the systemd timer from the new path.

```bash
cd /mnt/ssd/projects/mystmon
bash ops/install-systemd-timer.sh
```

7. If cron is still required instead of systemd, reinstall the cron entry from the new path.

```bash
crontab -l > /tmp/mystmon-cron || true
grep -v 'mystmon' /tmp/mystmon-cron > /tmp/mystmon-cron.clean || true
mv /tmp/mystmon-cron.clean /tmp/mystmon-cron
cat ops/mystmon.cron >> /tmp/mystmon-cron
crontab /tmp/mystmon-cron
```

8. Validate the installation.

```bash
cd /mnt/ssd/projects/mystmon
./ops/validate-mystmon.sh
sudo systemctl --no-pager --full status mystmon.service mystmon.timer || true
docker compose ps mystmon
```

## Post-Checks

Confirm:

- `WorkingDirectory` resolves to `/mnt/ssd/projects/mystmon`
- `MYSTMON_REMOTE_DIR` in `.env` matches `/mnt/ssd/projects/mystmon` if used
- generated files appear under `/mnt/ssd/projects/mystmon/data/`
- any SNMP or Telegraf integration reads the new `snmp_extend.txt` path

## Common Risks

- leaving an old cron entry pointing at `/mnt/ssd/codex/mystmon`
- losing the live `.env` during a directory move
- reinstalling systemd units without reloading or restarting them
- assuming the new checkout is authoritative when the old path contains the live runtime state

## Safe Rollback

If validation fails and the old tree still exists intact:

1. stop the timer/service
2. move the directory back to `/mnt/ssd/codex/mystmon`
3. restore the old cron or systemd configuration
4. validate from the old path before retrying
