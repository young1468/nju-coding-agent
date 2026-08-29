from __future__ import annotations

from copy import deepcopy
from typing import Any

from coding_agent.agent import MAX_STEPS, CodingAgent, PHASE_TWO_TOOL_RESULT, SYSTEM_MESSAGE
from coding_agent.client import AssistantResponse


class FakeModel:
    def __init__(self, responses: list[AssistantResponse | Exception]) -> None:
        self._responses = responses
        self.requests: list[list[dict[str, Any]]] = []

    def complete(self, messages: list[dict[str, Any]]) -> AssistantResponse:
        self.requests.append(deepcopy(messages))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def tool_response(call_id: str = "call-1") -> AssistantResponse:
    return AssistantResponse(
        content=None,
        tool_calls=[
            {
                "id": call_id,
                "type": "function",
                "function": {"name": "placeholder", "arguments": "{}"},
            }
        ],
    )


def test_agent_builds_initial_history_and_completes() -> None:
    model = FakeModel([AssistantResponse(content="Finished", tool_calls=[])])

    result = CodingAgent(model).run("Fix the test")

    assert result.status == "completed"
    assert result.answer == "Finished"
    assert model.requests == [[
        {"role": "system", "content": SYSTEM_MESSAGE},
        {"role": "user", "content": "Fix the test"},
    ]]
    assert result.messages[-1] == {"role": "assistant", "content": "Finished"}


def test_agent_records_unavailable_tool_result_then_continues() -> None:
    model = FakeModel([tool_response(), AssistantResponse(content="Cannot run it yet", tool_calls=[])])

    result = CodingAgent(model).run("Run tests")

    assert result.status == "completed"
    assert len(model.requests) == 2
    assert model.requests[1][-1]["role"] == "tool"
    assert PHASE_TWO_TOOL_RESULT in model.requests[1][-1]["content"]


def test_agent_stops_after_maximum_tool_interaction_steps() -> None:
    model = FakeModel([tool_response(str(index)) for index in range(MAX_STEPS)])

    result = CodingAgent(model).run("Keep trying")

    assert result.status == "max_steps"
    assert len(model.requests) == MAX_STEPS


def test_agent_returns_clear_result_when_model_raises() -> None:
    model = FakeModel([RuntimeError("offline")])

    result = CodingAgent(model).run("Fix it")

    assert result.status == "error"
    assert result.answer == "Model request failed. Check the model configuration and service."


def test_agent_rejects_empty_model_response() -> None:
    model = FakeModel([AssistantResponse(content=None, tool_calls=[])])

    result = CodingAgent(model).run("Fix it")

    assert result.status == "error"
    assert result.answer == "Model returned neither text nor tool calls."
