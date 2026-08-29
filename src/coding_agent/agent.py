"""Minimal agent loop and conversation history management."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from typing import Any, Protocol

from .client import AssistantResponse
from .schemas import TOOL_SCHEMAS
from .tools import ToolDispatcher, ToolResult, truncate_output

MAX_STEPS = 12
SYSTEM_MESSAGE = (
    "You are a coding assistant. Explain your work clearly and only claim actions "
    "that have been completed."
)
class ModelClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AssistantResponse: ...


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
        dispatcher: ToolDispatcher,
        max_steps: int = MAX_STEPS,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        self._client = client
        self._dispatcher = dispatcher
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
                response = self._client.complete(messages, tools=TOOL_SCHEMAS)
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
                for tool_call in response.tool_calls:
                    call_id = tool_call["id"]
                    if call_id is None:
                        return AgentResult(
                            status="error",
                            answer="Model returned a tool call without an identifier.",
                            messages=messages,
                        )
                    result = self._execute_tool(tool_call)
                    self._log_tool_result(tool_steps, result)
                    messages.append(
                        {"role": "tool", "tool_call_id": call_id, "content": result.to_json()}
                    )
                if tool_steps >= self._max_steps:
                    return AgentResult(
                        status="max_steps",
                        answer="Stopped after reaching the maximum tool interaction steps.",
                        messages=messages,
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

    def _execute_tool(self, tool_call: dict[str, Any]) -> ToolResult:
        function = tool_call["function"]
        tool_name = function["name"]
        try:
            arguments = json.loads(function["arguments"])
        except json.JSONDecodeError:
            return ToolResult(
                success=False,
                tool=tool_name,
                error="Tool arguments were not valid JSON.",
            )
        self._log(f"tool={tool_name} args={_log_arguments(arguments)}")
        return self._dispatcher.execute(tool_name, arguments)

    def _log_tool_result(self, step: int, result: ToolResult) -> None:
        summary = result.error or json.dumps(result.result, ensure_ascii=False)
        self._log(f"[step {step}] result={truncate_output(summary, 300)}")


def _assistant_message(response: AssistantResponse) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": response.content}
    if response.tool_calls:
        message["tool_calls"] = response.tool_calls
    return message


def _log_arguments(arguments: object) -> str:
    if not isinstance(arguments, dict):
        return "<invalid JSON object>"

    safe_arguments: dict[str, object] = {}
    for name, value in arguments.items():
        if name.lower() in {"api_key", "authorization", "token", "secret", "password"}:
            safe_arguments[name] = "<redacted>"
        elif name == "content" and isinstance(value, str):
            safe_arguments[name] = f"<{len(value)} characters>"
        else:
            safe_arguments[name] = value
    return truncate_output(json.dumps(safe_arguments, ensure_ascii=False), 300)
