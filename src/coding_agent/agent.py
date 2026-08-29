"""Minimal agent loop and conversation history management."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from typing import Any, Protocol

from .client import AssistantResponse

MAX_STEPS = 12
SYSTEM_MESSAGE = (
    "You are a coding assistant. Explain your work clearly and only claim actions "
    "that have been completed."
)
PHASE_TWO_TOOL_RESULT = "Phase 2 has not implemented local tool execution."


class ModelClient(Protocol):
    def complete(self, messages: list[dict[str, Any]]) -> AssistantResponse: ...


@dataclass(frozen=True)
class AgentResult:
    status: str
    answer: str
    messages: list[dict[str, Any]]


class CodingAgent:
    """Owns one conversation and orchestrates model requests."""

    def __init__(
        self,
        client: ModelClient,
        max_steps: int = MAX_STEPS,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        self._client = client
        self._max_steps = max_steps
        self._logger = logger

    def run(self, task: str) -> AgentResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": task},
        ]
        tool_steps = 0

        while True:
            self._log(f"Agent step {tool_steps + 1}: requesting model.")
            try:
                response = self._client.complete(messages)
            except Exception:
                return AgentResult(
                    status="error",
                    answer="Model request failed. Check the model configuration and service.",
                    messages=messages,
                )

            messages.append(_assistant_message(response))
            if response.tool_calls:
                tool_steps += 1
                self._log(f"Agent step {tool_steps}: model returned tool calls.")
                if tool_steps >= self._max_steps:
                    return AgentResult(
                        status="max_steps",
                        answer="Stopped after reaching the maximum tool interaction steps.",
                        messages=messages,
                    )

                for tool_call in response.tool_calls:
                    call_id = tool_call["id"]
                    if call_id is None:
                        return AgentResult(
                            status="error",
                            answer="Model returned a tool call without an identifier.",
                            messages=messages,
                        )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": json.dumps(
                                {"status": "unavailable", "message": PHASE_TWO_TOOL_RESULT}
                            ),
                        }
                    )
                continue

            if response.content:
                self._log("Agent returned a final answer.")
                return AgentResult(
                    status="completed", answer=response.content, messages=messages
                )

            return AgentResult(
                status="error",
                answer="Model returned neither text nor tool calls.",
                messages=messages,
            )

    def _log(self, message: str) -> None:
        if self._logger is not None:
            self._logger(message)


def _assistant_message(response: AssistantResponse) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": response.content}
    if response.tool_calls:
        message["tool_calls"] = response.tool_calls
    return message
