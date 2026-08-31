from __future__ import annotations

import json

import pytest

from coding_agent.session import SessionError, SessionStore, build_model_messages, delete_session_file, inspect_session, list_session_summaries


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


def test_session_summary_lists_valid_and_invalid_files(tmp_path) -> None:
    workspace = tmp_path / "workspace"; workspace.mkdir()
    sessions = tmp_path / "sessions"; sessions.mkdir()
    valid = sessions / "valid.jsonl"
    store = SessionStore(valid, workspace)
    store.initialize([{"role": "system", "content": "rules"}, {"role": "user", "content": "A long initial task for the project"}])
    store.append_message({"role": "assistant", "content": "Latest answer"})
    bad = sessions / "bad.jsonl"; bad.write_text("{bad\n", encoding="utf-8")
    summary = inspect_session(valid, preview_chars=12)
    assert summary.recoverable and summary.workspace == str(workspace.resolve())
    assert summary.title.endswith("...") and summary.preview.endswith("...")
    summaries = list_session_summaries(sessions)
    assert {item.path.name for item in summaries} == {"valid.jsonl", "bad.jsonl"}
    assert any(not item.recoverable for item in summaries)


def test_session_summary_marks_incompatible_headers_unrecoverable(tmp_path) -> None:
    sessions = tmp_path / "sessions"; sessions.mkdir()
    unsupported = sessions / "unsupported.jsonl"
    unsupported.write_text('{"type":"session","version":99,"workspace":"x"}\n', encoding="utf-8")
    missing_workspace = sessions / "missing-workspace.jsonl"
    missing_workspace.write_text('{"type":"session","version":1}\n', encoding="utf-8")

    assert not inspect_session(unsupported).recoverable
    assert not inspect_session(missing_workspace).recoverable


def test_session_metadata_is_append_only_and_messages_remain_compatible(tmp_path) -> None:
    workspace = tmp_path / "workspace"; workspace.mkdir()
    path = tmp_path / "session.jsonl"
    store = SessionStore(path, workspace)
    messages = [{"role": "system", "content": "rules"}, {"role": "user", "content": "Fix it"}]
    store.initialize(messages)
    store.set_title("Fix calculator behavior")
    store.append_log("tool result: read_file")

    assert store.load_messages() == messages
    assert store.load_title() == "Fix calculator behavior"
    assert store.load_logs() == ["tool result: read_file"]
    summary = inspect_session(path)
    assert summary.title == "Fix calculator behavior"
    assert summary.logs == ("tool result: read_file",)


def test_delete_session_file_removes_only_direct_jsonl_children(tmp_path) -> None:
    sessions = tmp_path / "sessions"; sessions.mkdir()
    valid = sessions / "valid.jsonl"; valid.write_text("{}\n", encoding="utf-8")
    nested = sessions / "nested"; nested.mkdir()
    nested_file = nested / "nested.jsonl"; nested_file.write_text("{}\n", encoding="utf-8")
    outside = tmp_path / "outside.jsonl"; outside.write_text("{}\n", encoding="utf-8")

    delete_session_file(valid, sessions)
    assert not valid.exists()
    for invalid in (nested_file, outside, sessions / "notes.txt", sessions):
        with pytest.raises(SessionError, match="direct .jsonl"):
            delete_session_file(invalid, sessions)
    assert nested_file.exists() and outside.exists()
