from coding_agent.config import Settings


def test_settings_reads_model_environment_variables() -> None:
    settings = Settings.from_env(
        {
            "AGENT_API_KEY": "test-key",
            "AGENT_BASE_URL": "https://example.invalid/v1",
            "AGENT_MODEL": "test-model",
        }
    )

    assert settings.api_key == "test-key"
    assert settings.base_url == "https://example.invalid/v1"
    assert settings.model == "test-model"


def test_settings_allows_missing_model_configuration() -> None:
    assert Settings.from_env({}) == Settings(None, None, None)
