from __future__ import annotations

from copy import deepcopy
import json
import sys
from typing import Any

from coding_agent.agent import MAX_STEPS, CodingAgent, SYSTEM_MESSAGE
from coding_agent.client import AssistantResponse
from coding_agent.schemas import TOOL_SCHEMAS
from coding_agent.session import SessionStore
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


def test_compaction_is_not_repeated_for_each_agent_step(tmp_path) -> None:
    workspace = tmp_path
    session = SessionStore(tmp_path / "session.jsonl", workspace)
    history = [{"role": "system", "content": SYSTEM_MESSAGE}]
    for _ in range(3):
        history.extend([{"role": "user", "content": "old task " * 20}, {"role": "assistant", "content": "old answer " * 20}])
    session.initialize(history)
    model = FakeModel([AssistantResponse(content="summary", tool_calls=[]), tool_response(), AssistantResponse(content="done", tool_calls=[])])

    result = CodingAgent(
        model,
        ToolDispatcher(workspace),
        session_store=session,
        max_context_chars=200,
        recent_context_chars=100,
        reserve_tokens=0,
    ).run("new task")

    assert result.status == "completed"
    assert sum(1 for messages, tools in zip(model.requests, model.tool_schemas) if tools is None) == 1


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


def test_review_and_plan_modes_only_expose_read_tools_and_reject_writes(tmp_path) -> None:
    for mode in ("review", "plan"):
        model = FakeModel([tool_response(name="write_file", arguments='{"path": "bad.txt", "content": "no"}'), AssistantResponse(content="Done", tool_calls=[])])
        result = CodingAgent(model, ToolDispatcher(tmp_path), mode=mode).run("Inspect this project")
        assert [schema["function"]["name"] for schema in model.tool_schemas[0]] == ["list_files", "read_file"]
        assert any(message.get("role") == "system" and mode.title() in message.get("content", "") for message in model.requests[0])
        assert json.loads([message for message in result.messages if message["role"] == "tool"][0]["content"])["success"] is False
        assert not (tmp_path / "bad.txt").exists()


def test_plan_mode_can_read_files_before_returning_a_plan(tmp_path) -> None:
    (tmp_path / "app.py").write_text("STATUS = 'broken'\n", encoding="utf-8")
    model = FakeModel([
        tool_response(name="read_file", arguments='{"path": "app.py"}'),
        AssistantResponse(content="1. Update STATUS. 2. Run the existing test.", tool_calls=[]),
    ])

    result = CodingAgent(model, ToolDispatcher(tmp_path), mode="plan").run("Plan the fix")

    assert result.status == "completed"
    assert "Update STATUS" in result.answer
    tool_result = json.loads([message for message in result.messages if message["role"] == "tool"][0]["content"])
    assert tool_result["success"] is True
