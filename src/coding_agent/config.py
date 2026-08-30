"""Runtime configuration loaded from environment variables or a local .env file."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import dotenv_values


class ConfigurationError(ValueError):
    """Raised when required model configuration is absent."""


@dataclass(frozen=True)
class Settings:
    """Model settings from environment variables with a local .env fallback."""

    api_key: str | None
    base_url: str | None
    model: str | None

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        dotenv_path: str | Path | None = None,
    ) -> "Settings":
        """Load .env values only when the corresponding environment value is absent."""
        source = os.environ if environ is None else environ
        # Explicit mappings are used by tests/callers as complete configuration sources.
        load_dotenv = environ is None
        env_file = Path(dotenv_path) if dotenv_path is not None else Path.cwd() / ".env"
        file_values = dotenv_values(env_file) if (load_dotenv or dotenv_path is not None) and env_file.is_file() else {}

        def value(name: str) -> str | None:
            environment_value = source.get(name)
            if environment_value is not None:
                return environment_value
            file_value = file_values.get(name)
            return file_value if isinstance(file_value, str) else None

        return cls(
            api_key=value("AGENT_API_KEY"),
            base_url=value("AGENT_BASE_URL"),
            model=value("AGENT_MODEL"),
        )

    def require_model_config(self) -> None:
        missing = [
            name
            for name, value in (
                ("AGENT_API_KEY", self.api_key),
                ("AGENT_BASE_URL", self.base_url),
                ("AGENT_MODEL", self.model),
            )
            if not value
        ]
        if missing:
            raise ConfigurationError(
                "Missing required model configuration: " + ", ".join(missing)
            )