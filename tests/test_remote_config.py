from mystmon.config import MystMonConfig


def test_remote_host_config_uses_password_env_not_secret_value() -> None:
    config = MystMonConfig.model_validate(
        {
            "myst": {
                "remote_hosts": [
                    {
                        "host": "192.168.1.173",
                        "user": "sundeep",
                        "password_env": "MYSTMON_SSH_PASSWORD",
                    }
                ]
            }
        }
    )

    assert config.myst.remote_hosts[0].password_env == "MYSTMON_SSH_PASSWORD"
