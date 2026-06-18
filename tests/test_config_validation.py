import pytest

from mystmon.config import MystCollectorConfig


def test_tequilapi_endpoint_config_rejects_non_get_methods() -> None:
    with pytest.raises(ValueError, match="must use GET"):
        MystCollectorConfig.model_validate(
            {
                "api_endpoints": [
                    {"name": "bad", "path": "/healthcheck", "metric_prefix": "bad", "method": "POST"},
                ]
            }
        )


def test_tequilapi_endpoint_config_rejects_risky_paths() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        MystCollectorConfig.model_validate(
            {
                "api_endpoints": [
                    {"name": "bad", "path": "/auth/login", "metric_prefix": "bad", "method": "GET"},
                ]
            }
        )


def test_tequilapi_endpoint_config_preserves_query_string() -> None:
    config = MystCollectorConfig.model_validate(
        {
            "api_endpoints": [
                {"name": "sessions_1d", "path": "/node/provider/sessions-count?range=1d", "metric_prefix": "provider", "method": "GET"},
            ]
        }
    )

    assert config.api_endpoints[0].path == "/node/provider/sessions-count?range=1d"
