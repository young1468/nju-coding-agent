from __future__ import annotations

from copy import deepcopy
import json
import sys
from typing import Any

from coding_agent.agent import CodingAgent
from coding_agent.client import AssistantResponse
from coding_agent.tools import ToolDispatcher


class FakeModel:
    def __init__(self, responses: list[AssistantResponse]) -> None:
        self._responses = responses
        self.requests: list[list[dict[str, Any]]] = []

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AssistantResponse:
        self.requests.append(deepcopy(messages))
        return self._responses.pop(0)


def tool_call(call_id: str, name: str, arguments: dict[str, Any]) -> AssistantResponse:
    return AssistantResponse(
        content=None,
        tool_calls=[
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    )


def test_agent_repairs_failing_pytest_project_in_temporary_workspace(tmp_path) -> None:
    source = tmp_path / "calculator.py"
    test_file = tmp_path / "test_calculator.py"
    source.write_text("def add(left, right):\n    return left - right\n", encoding="utf-8")
    original_test = "from calculator import add\n\n\ndef test_adds_two_numbers():\n    assert add(1, 2) == 3\n"
    test_file.write_text(original_test, encoding="utf-8")
    pytest_command = {"program": sys.executable, "args": ["-m", "pytest", "-q"]}
    model = FakeModel(
        [
            tool_call("list", "list_files", {"path": "."}),
            tool_call("read", "read_file", {"path": "calculator.py"}),
            tool_call("test-before", "run_command", pytest_command),
            tool_call(
                "write",
                "write_file",
                {"path": "calculator.py", "content": "def add(left, right):\n    return left + right\n"},
            ),
            tool_call("test-after", "run_command", pytest_command),
            AssistantResponse(content="Fixed calculator.py and verified pytest passes.", tool_calls=[]),
        ]
    )

    result = CodingAgent(model, ToolDispatcher(tmp_path)).run(
        "Fix the failing tests without modifying test files"
    )

    assert result.status == "completed"
    assert source.read_text(encoding="utf-8") == "def add(left, right):\n    return left + right\n"
    assert test_file.read_text(encoding="utf-8") == original_test
    tool_results = [json.loads(message["content"]) for message in result.messages if message["role"] == "tool"]
    assert [item["tool"] for item in tool_results] == [
        "list_files",
        "read_file",
        "run_command",
        "write_file",
        "run_command",
    ]
    assert tool_results[2]["success"] is False
    assert tool_results[4]["success"] is True
    assert len(model.requests) == 6
