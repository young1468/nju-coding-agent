import pytest

from coding_agent.config import ConfigurationError, Settings


def test_settings_reads_non_sensitive_model_environment_variables() -> None:
    settings = Settings.from_env(
        {
            "AGENT_BASE_URL": "https://example.invalid/v1",
            "AGENT_MODEL": "test-model",
        }
    )

    assert settings.api_key is None
    assert settings.base_url == "https://example.invalid/v1"
    assert settings.model == "test-model"


def test_settings_allows_missing_model_configuration() -> None:
    assert Settings.from_env({}) == Settings(None, None, None)


def test_settings_reports_missing_required_model_configuration() -> None:
    with pytest.raises(ConfigurationError, match="AGENT_API_KEY"):
        Settings.from_env({}).require_model_config()
