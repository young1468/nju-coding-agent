"""Minimal agent loop and conversation history management."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from typing import Any, Protocol

from .client import AssistantResponse
from .schemas import TOOL_SCHEMAS
from .session import (
    MAX_CONTEXT_CHARS,
    RECENT_CONTEXT_CHARS,
    SessionError,
    SessionStore,
    build_model_messages,
)
from .tools import ToolDispatcher, ToolResult, truncate_output

MAX_STEPS = 12
SYSTEM_MESSAGE = (
    "You are a coding agent working inside the provided workspace.\n"
    "Rules:\n"
    "- Inspect relevant files before modifying them.\n"
    "- Use the available local tools instead of guessing about workspace contents.\n"
    "- Do not modify tests unless the user explicitly requests it.\n"
    "- Run relevant tests after making code changes.\n"
    "- Continue until the requested task is solved or a tool result makes it impossible.\n"
    "- Provide a concise final summary that only claims completed actions."
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
    """Owns a conversation and orchestrates model requests and local tools."""

    def __init__(
        self,
        client: ModelClient,
        dispatcher: ToolDispatcher,
        max_steps: int = MAX_STEPS,
        logger: Callable[[str], None] | None = None,
        session_store: SessionStore | None = None,
        max_context_chars: int = MAX_CONTEXT_CHARS,
        recent_context_chars: int = RECENT_CONTEXT_CHARS,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        self._client = client
        self._dispatcher = dispatcher
        self._max_steps = max_steps
        self._logger = logger
        self._session_store = session_store
        self._max_context_chars = max_context_chars
        self._recent_context_chars = recent_context_chars

    def run(self, task: str) -> AgentResult:
        try:
            messages = self._start_or_resume(task)
        except SessionError as error:
            return AgentResult(status="error", answer=f"Session error: {error}", messages=[])
        tool_steps = 0

        while True:
            self._log(f"[Agent Step {tool_steps + 1}] Requesting model")
            try:
                request_messages = build_model_messages(
                    messages, self._max_context_chars, self._recent_context_chars
                )
                response = self._client.complete(request_messages, tools=TOOL_SCHEMAS)
            except Exception:
                return AgentResult(
                    status="error",
                    answer="Model request failed. Check the model configuration and service.",
                    messages=messages,
                )

            try:
                self._append_message(messages, _assistant_message(response))
            except SessionError as error:
                return AgentResult(status="error", answer=f"Session error: {error}", messages=messages)

            if response.tool_calls:
                tool_steps += 1
                self._log(f"[Agent Step {tool_steps}] Assistant: tool call")
                for tool_call in response.tool_calls:
                    call_id = tool_call["id"]
                    if call_id is None:
                        return AgentResult(
                            status="error",
                            answer="Model returned a tool call without an identifier.",
                            messages=messages,
                        )
                    result = self._execute_tool(tool_call, tool_steps)
                    self._log_tool_result(tool_steps, result)
                    try:
                        self._append_message(
                            messages,
                            {"role": "tool", "tool_call_id": call_id, "content": result.to_json()},
                        )
                    except SessionError as error:
                        return AgentResult(status="error", answer=f"Session error: {error}", messages=messages)
                if tool_steps >= self._max_steps:
                    return AgentResult(
                        status="max_steps",
                        answer="Stopped after reaching the maximum tool interaction steps.",
                        messages=messages,
                    )
                continue

            if response.content:
                self._log("[Agent] Assistant: final answer")
                return AgentResult(status="completed", answer=response.content, messages=messages)

            return AgentResult(
                status="error",
                answer="Model returned neither text nor tool calls.",
                messages=messages,
            )

    def _start_or_resume(self, task: str) -> list[dict[str, Any]]:
        if self._session_store is None:
            return [
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": task},
            ]
        if self._session_store.exists():
            messages = self._session_store.load_messages()
            if not messages or messages[0].get("role") != "system":
                raise SessionError("Session history is missing its initial system message.")
            self._append_message(messages, {"role": "user", "content": task})
            return messages

        messages = [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": task},
        ]
        self._session_store.initialize(messages)
        return messages

    def _append_message(self, messages: list[dict[str, Any]], message: dict[str, Any]) -> None:
        messages.append(message)
        if self._session_store is not None:
            self._session_store.append_message(message)

    def _log(self, message: str) -> None:
        if self._logger is not None:
            self._logger(message)

    def _execute_tool(self, tool_call: dict[str, Any], step: int) -> ToolResult:
        function = tool_call["function"]
        tool_name = function["name"]
        try:
            arguments = json.loads(function["arguments"])
        except json.JSONDecodeError:
            return ToolResult(success=False, tool=tool_name, error="Tool arguments were not valid JSON.")
        self._log(f"[Agent Step {step}] Tool: {tool_name}")
        self._log(f"[Agent Step {step}] Arguments: {_log_arguments(arguments)}")
        return self._dispatcher.execute(tool_name, arguments)

    def _log_tool_result(self, step: int, result: ToolResult) -> None:
        self._log(f"[Agent Step {step}] Result: {_tool_result_summary(result)}")


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


def _tool_result_summary(result: ToolResult) -> str:
    summary: dict[str, object] = {"success": result.success, "tool": result.tool}
    if result.error is not None:
        summary["error"] = result.error
    elif result.result is not None:
        for name, value in result.result.items():
            summary[name] = f"<{len(value)} characters>" if name in {"content", "stdout", "stderr"} and isinstance(value, str) else value
    return truncate_output(json.dumps(summary, ensure_ascii=False), 300)