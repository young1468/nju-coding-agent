"""Thin OpenAI-compatible chat client wrapper."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from .config import Settings


class LLMClientError(RuntimeError):
    """Raised when a model response cannot be obtained or understood."""

    def __init__(self, message: str, *, context_overflow: bool = False) -> None:
        super().__init__(message)
        self.context_overflow = context_overflow


@dataclass(frozen=True)
class AssistantResponse:
    """The subset of a model response required by the agent loop."""

    content: str | None
    tool_calls: list[dict[str, Any]]


class OpenAICompatibleClient:
    """Send one chat-completion request at a time without retaining history."""

    def __init__(self, model: str, completions: Any) -> None:
        self._model = model
        self._completions = completions

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAICompatibleClient":
        settings.require_model_config()
        try:
            sdk_client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
        except Exception as error:
            raise LLMClientError("Unable to initialize the model client.") from error
        return cls(model=settings.model or "", completions=sdk_client.chat.completions)

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] | None = None,
    ) -> AssistantResponse:
        request: dict[str, Any] = {
            "model": self._model,
            "messages": [dict(message) for message in messages],
        }
        if tools is not None:
            request["tools"] = [dict(tool) for tool in tools]
        try:
            response = self._completions.create(**request)
        except Exception as error:
            text = str(error).lower()
            overflow = any(token in text for token in ("context length", "context window", "prompt is too long", "maximum context", "too many tokens"))
            raise LLMClientError("Model request failed: context is too large." if overflow else "Model request failed.", context_overflow=overflow) from error
        return _parse_response(response)


def _parse_response(response: Any) -> AssistantResponse:
    choices = _get_value(response, "choices")
    if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)) or not choices:
        raise LLMClientError("Model response did not contain a completion choice.")

    message = _get_value(choices[0], "message")
    if message is None:
        raise LLMClientError("Model response did not contain an assistant message.")

    content = _get_value(message, "content")
    if content is not None and not isinstance(content, str):
        raise LLMClientError("Model response content had an unexpected type.")

    raw_tool_calls = _get_value(message, "tool_calls", []) or []
    if not isinstance(raw_tool_calls, Sequence) or isinstance(raw_tool_calls, (str, bytes)):
        raise LLMClientError("Model tool calls had an unexpected structure.")

    tool_calls = [_normalize_tool_call(tool_call) for tool_call in raw_tool_calls]
    return AssistantResponse(content=content, tool_calls=tool_calls)


def _normalize_tool_call(tool_call: Any) -> dict[str, Any]:
    function = _get_value(tool_call, "function")
    if function is None:
        raise LLMClientError("A model tool call did not contain function details.")

    name = _get_value(function, "name")
    arguments = _get_value(function, "arguments")
    if not isinstance(name, str) or not isinstance(arguments, str):
        raise LLMClientError("A model tool call had invalid function details.")

    call_id = _get_value(tool_call, "id")
    if call_id is not None and not isinstance(call_id, str):
        raise LLMClientError("A model tool call had an invalid identifier.")

    return {
        "id": call_id,
        "type": _get_value(tool_call, "type", "function"),
        "function": {"name": name, "arguments": arguments},
    }


def _get_value(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)
