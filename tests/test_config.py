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


def test_settings_loads_values_from_dotenv_file(tmp_path) -> None:
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(
        "AGENT_API_KEY=file-test-key\nAGENT_BASE_URL=https://file.invalid/v1\nAGENT_MODEL=file-model\n",
        encoding="utf-8",
    )

    settings = Settings.from_env({}, dotenv_path=dotenv_file)

    assert settings == Settings("file-test-key", "https://file.invalid/v1", "file-model")


def test_environment_values_override_dotenv_values(tmp_path) -> None:
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(
        "AGENT_API_KEY=file-test-key\nAGENT_BASE_URL=https://file.invalid/v1\nAGENT_MODEL=file-model\n",
        encoding="utf-8",
    )

    settings = Settings.from_env(
        {"AGENT_API_KEY": "environment-test-key", "AGENT_MODEL": "environment-model"},
        dotenv_path=dotenv_file,
    )

    assert settings == Settings(
        "environment-test-key", "https://file.invalid/v1", "environment-model"
    )