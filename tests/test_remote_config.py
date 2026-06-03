from mystmon.config import MystMonConfig


def test_remote_host_config_uses_password_env_not_secret_value() -> None:
    config = MystMonConfig.model_validate(
        {
            "myst": {
                "remote_hosts": [
                    {
                        "host": "remote-host-1",
                        "user": "username",
                        "password_env": "MYSTMON_SSH_PASSWORD",
                    }
                ]
            }
        }
    )

    assert config.myst.remote_hosts[0].password_env == "MYSTMON_SSH_PASSWORD"
