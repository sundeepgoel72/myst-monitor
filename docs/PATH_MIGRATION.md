# MystMon Path Migration

This checklist migrates a local MystMon deployment from an older install path to the current checkout path used by the helper scripts.

Old path:

```text
<legacy-repo-dir>
```

New path:

```text
<current-repo-dir>
```

Use this only if your existing install still points at the legacy directory.

## Pre-checks

1. Confirm the service is currently stopped or can tolerate a short restart window.
2. Confirm the new checkout exists and contains the current release.
3. Confirm your local `.env` and `config.yaml` are present in the new checkout.

## Migration

1. Stop any running service or timer that points at the old path.
2. Move or re-clone the repository into the new path.
3. Copy local-only files into place if needed:
   - `.env`
   - `config.yaml`
   - `data/`
4. Reinstall the service or timer from the new checkout:
   - `./ops/install-remote.sh`
   - `./ops/install-systemd-timer.sh`
5. Validate the deployment:
   - `docker compose ps`
   - `./ops/validate-mystmon.sh`

## Rollback

If the migration fails, restore the previous checkout path and reinstall the old service definitions. Keep the local-only config files in the ignored path so the rollback can reuse them.
