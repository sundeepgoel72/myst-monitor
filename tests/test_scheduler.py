import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

from mystmon.config import MystMonConfig
from mystmon.config import MystCollectorConfig
from mystmon.config import MystNodesPortalAccountConfig
from mystmon.bootstrap import bootstrap_storage
from mystmon.scheduler import CollectorScheduler
from mystmon.history import HistoryStore
from mystmon.storage import ReadingStore


def test_collector_scheduler_collect_once():
    """Test that CollectorScheduler.collect_once can be called successfully."""
    # Create a minimal config
    config = MystMonConfig()
    
    # Create mock stores
    store = ReadingStore()
    
    # Create scheduler
    scheduler = CollectorScheduler(config, store)
    
    with patch('mystmon.scheduler.collect_mystnodes_portal_accounts', new=AsyncMock(return_value=None)):
        # This should not raise an exception
        result = asyncio.run(scheduler.collect_once())
        
        # Verify the result structure
        assert isinstance(result, dict)
        assert "myst" in result


def test_collector_scheduler_with_myst_config():
    """Test scheduler with myst config enabled."""
    # Create config with myst enabled
    config = MystMonConfig(myst=MystCollectorConfig(enabled=True, api_probe_enabled=False, containers=[], remote_hosts=[]))
    
    # Create mock stores
    store = ReadingStore()
    
    # Create scheduler
    scheduler = CollectorScheduler(config, store)
    
    with patch('mystmon.scheduler.collect_mystnodes_portal_accounts', new=AsyncMock(return_value=None)):
        result = asyncio.run(scheduler.collect_once())
        
        # Verify myst collection was attempted
        assert "myst" in result


def test_collector_scheduler_persists_mystnodes_payload_and_temp_file(tmp_path):
    config = MystMonConfig()
    config.service.data_dir = str(tmp_path)
    config.outputs.latest_json_path = str(tmp_path / "latest.json")
    config.outputs.snmp_extend_path = str(tmp_path / "snmp_extend.txt")
    config.history.enabled = True
    config.history.db_path = str(tmp_path / "history.db")
    config.mystnodes_accounts = [MystNodesPortalAccountConfig(account="account-a", password="secret")]

    bootstrap_storage(config.history.db_path, config.outputs.latest_json_path, config.outputs.snmp_extend_path)
    store = ReadingStore()
    history = HistoryStore(config.history.db_path)
    scheduler = CollectorScheduler(config, store, history=history)

    myst_nodes = [
        {
            "name": "node-a",
            "container_name": "node-a",
            "host": "192.168.1.10",
            "networks": [{"name": "host", "ip_address": "192.168.1.10"}],
            "ports": [{"container_port": 4050, "host_port": 4050}],
            "running": True,
            "restart_count": 0,
            "uptime_seconds": 123,
            "log_counts": {"error_or_warning": 0, "promise": 0, "session": 0, "identity_warning": 0},
        }
    ]
    mystnodes_portal = {
        "accounts": [{"name": "account-a", "authenticated": True, "endpoints": {"nodes": {"data": {"nodes": [{"id": "portal-1", "identity": "identity-1", "localIp": "192.168.1.10", "name": "node-a"}]}}}}],
        "nodes": [{"id": "portal-1", "identity": "identity-1", "localIp": "192.168.1.10", "name": "node-a", "account": "account-a"}],
        "authenticated": True,
        "endpoints": {},
        "node_details": {"nodes": {}},
    }

    async def fake_collect_mystnodes_portal_accounts(*args, **kwargs):
        return mystnodes_portal

    async def fake_collect_portal_local_nodes(*args, **kwargs):
        return [
            {
                "name": "node-a",
                "container_name": "node-a",
                "host": "192.168.1.10",
                "running": True,
                "restart_count": 0,
                "uptime_seconds": None,
                "warnings": [],
                "tequilapi": {"up": True, "metrics": {"provider_quality": 2.5}, "identity": "identity-1", "endpoints": {"healthcheck": {"data": {"version": "1.0.0"}}}},
            }
        ]

    with patch("mystmon.scheduler.collect_mystnodes_portal_accounts", new=fake_collect_mystnodes_portal_accounts), \
         patch.object(CollectorScheduler, "_collect_portal_local_nodes", new=fake_collect_portal_local_nodes):
        result = asyncio.run(scheduler.collect_once())

    assert result["myst"] == 1

    conn = history._connect()
    with conn:
        row = conn.execute("select snapshot_json from collections order by id desc limit 1").fetchone()
    snapshot = json.loads(row[0])
    assert snapshot["mystnodes"]["nodes"][0]["account"] == "account-a"


def test_scheduler_build_snapshot_dedupes_raw_runtime_nodes_and_applies_portal_match() -> None:
    scheduler = CollectorScheduler(MystMonConfig(), ReadingStore())
    raw_one = {
        "name": "node-a",
        "container_name": "node-a",
        "host": "192.168.1.10",
        "running": True,
        "status": "running",
        "api": {"up": True, "metrics": {"provider_quality": 2.5}},
    }
    raw_two = {
        "name": "node-a",
        "container_name": "node-a",
        "host": "192.168.1.10",
        "running": True,
        "status": "running",
        "api": {"up": True, "metrics": {"sessions_count_1d": 3}},
    }
    mystnodes_portal = {
        "nodes": [
            {
                "id": "portal-1",
                "identity": "identity-1",
                "localIp": "192.168.1.10",
                "name": "node-a",
                "account": "account-a",
            }
        ],
        "local_matches": {
            "portal-1": {
                "name": "node-a",
                "container_name": "node-a",
                "host": "192.168.1.10",
                "running": True,
                "status": "running",
                "api": {"up": True, "metrics": {"provider_quality": 2.5, "sessions_count_1d": 3}},
            }
        },
    }

    readings = [
        Mock(source_type="myst", raw_data=raw_one),
        Mock(source_type="myst", raw_data=raw_two),
    ]

    snapshot = scheduler._build_snapshot(readings, mystnodes_portal)

    assert len(snapshot["nodes"]) == 1
    assert snapshot["generated_at"].endswith("+05:30")
    node = snapshot["nodes"][0]
    assert node["local_match"] is True
    assert node["portal_account"] == "account-a"
    assert node["portal_identity"] == "identity-1"
    assert node["api"]["metrics"]["provider_quality"] == 2.5
    assert node["api"]["metrics"]["sessions_count_1d"] == 3
