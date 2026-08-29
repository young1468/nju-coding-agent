from __future__ import annotations

from types import SimpleNamespace

import pytest

from coding_agent.client import LLMClientError, OpenAICompatibleClient
from coding_agent.config import ConfigurationError, Settings


class FakeCompletions:
    def __init__(self, response: object | Exception) -> None:
        self.response = response
        self.request: dict[str, object] | None = None

    def create(self, **kwargs: object) -> object:
        self.request = kwargs
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_client_passes_model_and_messages_to_completion_api() -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Done", tool_calls=[]))]
    )
    completions = FakeCompletions(response)
    client = OpenAICompatibleClient("fake-model", completions)
    messages = [{"role": "user", "content": "Hello"}]

    result = client.complete(messages)

    assert result.content == "Done"
    assert result.tool_calls == []
    assert completions.request == {"model": "fake-model", "messages": messages}


def test_client_rejects_missing_settings_before_initialization() -> None:
    with pytest.raises(ConfigurationError, match="AGENT_API_KEY"):
        OpenAICompatibleClient.from_settings(Settings.from_env({}))


def test_client_wraps_completion_api_errors() -> None:
    client = OpenAICompatibleClient("fake-model", FakeCompletions(RuntimeError("offline")))

    with pytest.raises(LLMClientError, match="Model request failed"):
        client.complete([])


def test_client_rejects_malformed_responses() -> None:
    client = OpenAICompatibleClient("fake-model", FakeCompletions(SimpleNamespace(choices=[])))

    with pytest.raises(LLMClientError, match="completion choice"):
        client.complete([])
