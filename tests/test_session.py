from __future__ import annotations

import json

import pytest

from coding_agent.session import SessionError, SessionStore, build_model_messages


def test_session_store_round_trip(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = tmp_path / ".sessions" / "run.jsonl"
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "hello"},
    ]
    store = SessionStore(path, workspace)

    store.initialize(messages)
    store.append_message({"role": "assistant", "content": "done"})

    assert store.load_messages() == messages + [{"role": "assistant", "content": "done"}]
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert entries[0]["type"] == "session"
    assert all(entry["type"] == "message" for entry in entries[1:])


def test_session_store_rejects_corrupt_file_and_workspace_mismatch(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    corrupt_path = tmp_path / "corrupt.jsonl"
    corrupt_path.write_text("{bad\n", encoding="utf-8")

    with pytest.raises(SessionError, match="invalid JSON"):
        SessionStore(corrupt_path, workspace).load_messages()

    other_workspace = tmp_path / "other"
    other_workspace.mkdir()
    valid_path = tmp_path / "valid.jsonl"
    SessionStore(valid_path, workspace).initialize([])

    with pytest.raises(SessionError, match="workspace"):
        SessionStore(valid_path, other_workspace).load_messages()


def test_context_budget_keeps_latest_user_and_complete_tool_group() -> None:
    history = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "old " * 100},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "tool output " * 100},
        {"role": "user", "content": "latest task"},
        {"role": "assistant", "content": "latest answer"},
    ]

    result = build_model_messages(history, max_context_chars=180, recent_context_chars=100)

    assert result[0] == history[0]
    assert any(message.get("content") == "latest task" for message in result)
    assert any("Context notice" in message.get("content", "") for message in result)
    for index, message in enumerate(result):
        if message.get("role") == "tool":
            assert any(
                previous.get("role") == "assistant" and previous.get("tool_calls")
                for previous in result[:index]
            )
