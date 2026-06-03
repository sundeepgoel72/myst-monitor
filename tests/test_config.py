from mystmon.config import MystMonConfig, load_config


def test_default_poll_interval_is_six_hours() -> None:
    config = MystMonConfig()

    assert config.service.poll_interval_seconds == 21600


def test_snmp_target_requires_oids() -> None:
    payload = {
        "snmp": {
            "targets": [
                {
                    "name": "switch",
                    "host": "example-host",
                    "oids": {"sys_uptime": "1.3.6.1.2.1.1.3.0"},
                }
            ]
        }
    }

    config = MystMonConfig.model_validate(payload)

    assert config.snmp.targets[0].host == "example-host"


def test_myst_defaults_use_known_build_host() -> None:
    config = MystMonConfig()

    assert config.myst.enabled is True
    assert config.outputs.latest_json_path == "/data/mystmon/latest.json"


def test_inline_config_yaml_takes_precedence(monkeypatch, tmp_path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("service:\n  name: file-config\n", encoding="utf-8")
    monkeypatch.setenv("MYSTMON_CONFIG_YAML", "service:\n  name: inline-config\n")

    config = load_config(config_file)

    assert config.service.name == "inline-config"


def test_mystnodes_portal_config_defaults_to_disabled() -> None:
    config = MystMonConfig()

    assert config.mystnodes.enabled is False
    assert config.mystnodes.base_url == "https://my.mystnodes.com"
    assert config.mystnodes.email_env == "MYSTNODES_EMAIL"
    assert config.mystnodes.password_env == "MYSTNODES_PASSWORD"
    assert config.mystnodes.retry_count == 2
    assert config.mystnodes.retry_delay_seconds == 2.0
