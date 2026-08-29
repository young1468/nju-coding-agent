"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
import os


@dataclass(frozen=True)
class Settings:
    """Optional model settings reserved for later implementation phases."""

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
