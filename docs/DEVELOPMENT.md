# Development Setup

This project uses a normal local Python workflow for development. In this repo, WSL is the default development environment, but the same source setup also works on a standard Linux host.

## Local Source Setup

```bash
git clone https://github.com/sundeepgoel72/myst-monitor.git
cd myst-monitor
cp config.example.yaml config.yaml
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Use a single runtime config file: `config.yaml`.
If an older `config.local.yaml` exists from a previous setup, move any required values into `config.yaml` and delete the old file.

Verify imports:

```bash
.venv/bin/python -c "import mystmon.api; print('ok')"
```

## Focused Validation

```bash
PYTHONPATH=. .venv/bin/pytest tests/test_release_validation.py -q
PYTHONPATH=. .venv/bin/pytest \
  tests/test_release_validation.py \
  tests/test_config.py \
  tests/test_main.py \
  tests/test_history.py \
  tests/test_scheduler.py \
  tests/test_export_csv.py \
  tests/test_mystnodes_collector.py \
  tests/test_myst_local_discovery.py -q
```

Run the full suite:

```bash
PYTHONPATH=. .venv/bin/pytest
```

Shell syntax validation:

```bash
bash -n ops/build-on-linux.sh ops/install-remote.sh ops/validate-mystmon.sh
```
