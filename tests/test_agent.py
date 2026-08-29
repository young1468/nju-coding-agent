from __future__ import annotations

from copy import deepcopy
import json
import sys
from typing import Any

from coding_agent.agent import MAX_STEPS, CodingAgent, SYSTEM_MESSAGE
from coding_agent.client import AssistantResponse
from coding_agent.schemas import TOOL_SCHEMAS
from coding_agent.tools import ToolDispatcher


class FakeModel:
    def __init__(self, responses: list[AssistantResponse | Exception]) -> None:
        self._responses = responses
        self.requests: list[list[dict[str, Any]]] = []
        self.tool_schemas: list[list[dict[str, Any]] | None] = []

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AssistantResponse:
        self.requests.append(deepcopy(messages))
        self.tool_schemas.append(tools)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def tool_response(
    call_id: str = "call-1", name: str = "list_files", arguments: str = '{"path": "."}'
) -> AssistantResponse:
    return AssistantResponse(
        content=None,
        tool_calls=[
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        ],
    )


def test_agent_builds_initial_history_and_completes(tmp_path) -> None:
    model = FakeModel([AssistantResponse(content="Finished", tool_calls=[])])

    result = CodingAgent(model, ToolDispatcher(tmp_path)).run("Fix the test")

    assert result.status == "completed"
    assert result.answer == "Finished"
    assert model.requests == [[
        {"role": "system", "content": SYSTEM_MESSAGE},
        {"role": "user", "content": "Fix the test"},
    ]]
    assert model.tool_schemas == [TOOL_SCHEMAS]
    assert result.messages[-1] == {"role": "assistant", "content": "Finished"}


def test_agent_records_tool_result_then_continues(tmp_path) -> None:
    model = FakeModel([tool_response(), AssistantResponse(content="Cannot run it yet", tool_calls=[])])

    result = CodingAgent(model, ToolDispatcher(tmp_path)).run("Run tests")

    assert result.status == "completed"
    assert len(model.requests) == 2
    assert model.requests[1][-1]["role"] == "tool"
    assert json.loads(model.requests[1][-1]["content"])["success"] is True


def test_agent_stops_after_maximum_tool_interaction_steps(tmp_path) -> None:
    model = FakeModel([tool_response(str(index)) for index in range(MAX_STEPS)])

    result = CodingAgent(model, ToolDispatcher(tmp_path)).run("Keep trying")

    assert result.status == "max_steps"
    assert len(model.requests) == MAX_STEPS


def test_agent_returns_clear_result_when_model_raises(tmp_path) -> None:
    model = FakeModel([RuntimeError("offline")])

    result = CodingAgent(model, ToolDispatcher(tmp_path)).run("Fix it")

    assert result.status == "error"
    assert result.answer == "Model request failed. Check the model configuration and service."


def test_agent_rejects_empty_model_response(tmp_path) -> None:
    model = FakeModel([AssistantResponse(content=None, tool_calls=[])])

    result = CodingAgent(model, ToolDispatcher(tmp_path)).run("Fix it")

    assert result.status == "error"
    assert result.answer == "Model returned neither text nor tool calls."


def test_agent_runs_complete_local_tool_flow(tmp_path) -> None:
    (tmp_path / "app.py").write_text("STATUS = 'broken'\n", encoding="utf-8")
    model = FakeModel(
        [
            tool_response("call-list"),
            tool_response("call-read", "read_file", '{"path": "app.py"}'),
            tool_response(
                "call-fail",
                "run_command",
                json.dumps({"program": sys.executable, "args": ["-c", "import sys; sys.exit(1)"]}),
            ),
            tool_response(
                "call-write",
                "write_file",
                json.dumps({"path": "app.py", "content": "STATUS = 'fixed'\n"}),
            ),
            tool_response(
                "call-pass",
                "run_command",
                json.dumps(
                    {
                        "program": sys.executable,
                        "args": [
                            "-c",
                            "from pathlib import Path; assert 'fixed' in Path('app.py').read_text()",
                        ],
                    }
                ),
            ),
            AssistantResponse(content="The failing behavior was fixed and verified.", tool_calls=[]),
        ]
    )

    result = CodingAgent(model, ToolDispatcher(tmp_path)).run("Fix the failing test")

    assert result.status == "completed"
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "STATUS = 'fixed'\n"
    tool_messages = [message for message in result.messages if message["role"] == "tool"]
    assert [json.loads(message["content"])["tool"] for message in tool_messages] == [
        "list_files",
        "read_file",
        "run_command",
        "write_file",
        "run_command",
    ]
    assert json.loads(tool_messages[2]["content"])["success"] is False
    assert json.loads(tool_messages[-1]["content"])["success"] is True
