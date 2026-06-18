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


def test_mystnodes_accounts_default_to_empty() -> None:
    config = MystMonConfig()

    assert config.mystnodes_accounts == []


def test_local_config_overrides_tracked_config(tmp_path) -> None:
    config_file = tmp_path / "config.yaml"
    local_file = tmp_path / "config.local.yaml"
    config_file.write_text("service:\n  name: file-config\n", encoding="utf-8")
    local_file.write_text(
        'mystnodes_accounts:\n  - account: "account-a"\n    password: "secret"\n',
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.service.name == "file-config"
    assert len(config.mystnodes_accounts) == 1
    assert config.mystnodes_accounts[0].account == "account-a"


def test_mystnodes_multiple_accounts_config() -> None:
    config_dict = {
        "mystnodes_accounts": [
            {
                "account": "account1",
                "enabled": True,
                "password": "secret1",
                "wallet_address": "0x1111111111111111111111111111111111111111",
            },
            {
                "account": "account2",
                "enabled": True,
                "password": "secret2",
                "wallet_address": "0x2222222222222222222222222222222222222222",
            },
        ]
    }

    config = MystMonConfig.model_validate(config_dict)

    assert len(config.mystnodes_accounts) == 2
    assert config.mystnodes_accounts[0].account == "account1"
    assert config.mystnodes_accounts[1].account == "account2"


def test_mystnodes_accounts_require_env_refs() -> None:
    config_dict = {
        "mystnodes_accounts": [
            {
                "account": "account1",
                "enabled": True,
                "password": "secret",
            }
        ]
    }

    config = MystMonConfig.model_validate(config_dict)

    assert len(config.mystnodes_accounts) == 1
    assert config.mystnodes_accounts[0].account == "account1"
