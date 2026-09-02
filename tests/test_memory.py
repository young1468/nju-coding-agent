from __future__ import annotations

import json
from pathlib import Path

from coding_agent.client import AssistantResponse
from coding_agent.memory import MemoryCandidate, MemoryExtractor, MemoryManager, MemoryStore
from coding_agent.session import SessionStore
from coding_agent.agent import CodingAgent
from coding_agent.tools import ToolDispatcher


def test_memory_store_round_trip_and_index_metadata(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "workspace", global_root=tmp_path / "global")
    saved = store.save_candidates([
        MemoryCandidate("global", "user_profile", "用户偏好使用中文回答", ("language",), 0.9),
        MemoryCandidate("project", "project_context", "项目使用 Tkinter", ("architecture",), 0.8),
    ], source_session="session.jsonl")

    assert saved == 2
    assert "用户偏好使用中文回答" in store.read_markdown("global")
    assert store.load("project")[0].section == "project_context"
    index = json.loads(store.project_index_path.read_text(encoding="utf-8"))
    assert index["items"][0]["source_session"] == "session.jsonl"


def test_missing_or_corrupt_index_is_rebuilt_from_markdown(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "workspace", global_root=tmp_path / "global")
    store.save_candidates([MemoryCandidate("project", "decisions", "保留现有 CLI 接口")])
    store.project_index_path.write_text("not json", encoding="utf-8")

    items = store.load("project")

    assert [item.content for item in items] == ["保留现有 CLI 接口"]
    assert json.loads(store.project_index_path.read_text(encoding="utf-8"))["version"] == 1


def test_relevant_memory_prefers_project_and_respects_budget(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "workspace", global_root=tmp_path / "global")
    store.save_candidates([
        MemoryCandidate("global", "user_profile", "用户喜欢中文和简洁回答", ("language",)),
        MemoryCandidate("project", "conventions", "测试必须使用 pytest", ("testing",)),
        MemoryCandidate("project", "lessons", "金额计算必须使用 Decimal", ("money",)),
    ])

    loaded = store.load_relevant("请检查 pytest 的金额测试", max_chars=80)

    assert loaded.project_count == 2
    assert loaded.global_count == 1
    assert "project/conventions" in loaded.rendered
    assert len(loaded.rendered) <= 80


def test_memory_validation_rejects_sensitive_and_wrong_scope(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "workspace", global_root=tmp_path / "global")
    saved = store.save_candidates([
        MemoryCandidate("global", "project_context", "project fact"),
        MemoryCandidate("project", "conventions", "API_KEY=secret-value"),
        MemoryCandidate("global", "user_profile", "用户喜欢中文"),
    ])

    assert saved == 1
    assert store.load("global")[0].content == "用户喜欢中文"
    assert store.load("project") == []


class ExtractClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.tools = "unset"

    def complete(self, messages, tools=None):
        self.tools = tools
        return AssistantResponse(self.content, [])


def test_extractor_parses_json_and_disables_tools() -> None:
    client = ExtractClient(json.dumps({"memories": [{
        "scope": "global", "section": "user_profile", "content": "Prefer concise answers", "tags": ["style"]
    }]}))

    candidates = MemoryExtractor(client).extract("task", "done")

    assert candidates[0].content == "Prefer concise answers"
    assert client.tools is None


def test_agent_loads_and_extracts_memory_without_persisting_runtime_context(tmp_path: Path) -> None:
    class Manager:
        def __init__(self) -> None:
            self.loaded = False
            self.saved = False

        def load_for_task(self, task):
            self.loaded = True
            return type("Loaded", (), {"rendered": "[global/user_profile] Prefer concise answers", "global_count": 1, "project_count": 0})()

        def extract_and_save(self, *args, **kwargs):
            self.saved = True
            return 1

    class Model:
        def __init__(self) -> None:
            self.requests = []

        def complete(self, messages, tools=None):
            self.requests.append(messages)
            return AssistantResponse("done", [])

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = SessionStore(tmp_path / "session.jsonl", workspace)
    manager = Manager()
    model = Model()
    result = CodingAgent(model, ToolDispatcher(workspace), session_store=session, memory_manager=manager).run("Fix it")

    assert result.status == "completed"
    assert manager.loaded and manager.saved
    assert any("long_term_memory" in message.get("content", "") for message in model.requests[0])
    assert all("long_term_memory" not in message.get("content", "") for message in session.load_messages())
