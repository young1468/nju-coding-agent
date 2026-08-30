from __future__ import annotations

from coding_agent.agent import CodingAgent
from coding_agent.client import AssistantResponse
from coding_agent.session import SessionStore
from coding_agent.tools import ToolDispatcher


class _Model:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.requests = []

    def complete(self, messages, tools=None):
        self.requests.append(messages)
        return AssistantResponse(content=self.answer, tool_calls=[])


def test_agent_resumes_jsonl_session(tmp_path):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    session = SessionStore(tmp_path / 'session.jsonl', workspace)

    first_model = _Model('first')
    first = CodingAgent(first_model, ToolDispatcher(workspace), session_store=session).run('first task')
    assert first.status == 'completed'

    second_model = _Model('second')
    second = CodingAgent(second_model, ToolDispatcher(workspace), session_store=session).run('second task')
    assert second.status == 'completed'
    assert any(message.get('content') == 'first task' for message in second_model.requests[0])
    assert second_model.requests[0][-1] == {'role': 'user', 'content': 'second task'}
    assert [message.get('content') for message in session.load_messages() if message.get('role') == 'user'] == ['first task', 'second task']