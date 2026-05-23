from mystmon.config import MystMonConfig


def test_default_poll_interval_is_six_hours() -> None:
    config = MystMonConfig()

    assert config.service.poll_interval_seconds == 21600


def test_snmp_target_requires_oids() -> None:
    payload = {
        "snmp": {
            "targets": [
                {
                    "name": "switch",
                    "host": "192.168.1.72",
                    "oids": {"sys_uptime": "1.3.6.1.2.1.1.3.0"},
                }
            ]
        }
    }

    config = MystMonConfig.model_validate(payload)

    assert config.snmp.targets[0].host == "192.168.1.72"


def test_myst_defaults_use_known_build_host() -> None:
    config = MystMonConfig()

    assert config.myst.enabled is True
    assert config.outputs.latest_json_path == "/data/mystmon/latest.json"
