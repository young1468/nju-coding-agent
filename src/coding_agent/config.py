"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
import os


class ConfigurationError(ValueError):
    """Raised when required model configuration is absent."""


@dataclass(frozen=True)
class Settings:
    """Model settings supplied only through the process environment."""

    api_key: str | None
    base_url: str | None
    model: str | None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if environ is None else environ
        return cls(
            api_key=source.get("AGENT_API_KEY"),
            base_url=source.get("AGENT_BASE_URL"),
            model=source.get("AGENT_MODEL"),
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
