from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from coding_agent.tools import TRUNCATION_SUFFIX, ToolDispatcher, truncate_output


def make_dispatcher(workspace: Path, **kwargs: object) -> ToolDispatcher:
    return ToolDispatcher(workspace, **kwargs)


def test_list_files_and_read_file_return_workspace_content(tmp_path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    dispatcher = make_dispatcher(tmp_path)

    listing = dispatcher.execute("list_files", {"path": "."})
    reading = dispatcher.execute("read_file", {"path": "note.txt"})

    assert listing.success is True
    assert "[directory] nested" in listing.result["content"]
    assert "[file] note.txt" in listing.result["content"]
    assert reading.to_dict() == {
        "success": True,
        "tool": "read_file",
        "result": {"content": "hello"},
        "error": None,
    }
    assert json.loads(reading.to_json())["tool"] == "read_file"


def test_write_file_creates_parents_and_updates_content(tmp_path) -> None:
    dispatcher = make_dispatcher(tmp_path)

    result = dispatcher.execute("write_file", {"path": "nested/note.txt", "content": "hello"})

    assert result.success is True
    assert result.result["path"] == "nested\\note.txt"
    assert (tmp_path / "nested" / "note.txt").read_text(encoding="utf-8") == "hello"


def test_file_errors_and_invalid_arguments_are_structured(tmp_path) -> None:
    directory = tmp_path / "folder"
    directory.mkdir()
    dispatcher = make_dispatcher(tmp_path)

    missing = dispatcher.execute("read_file", {"path": "missing.txt"})
    missing_directory = dispatcher.execute("list_files", {"path": "missing-directory"})
    directory_read = dispatcher.execute("read_file", {"path": "folder"})
    invalid = dispatcher.execute("write_file", {"path": "new.txt", "content": 1})
    unknown = dispatcher.execute("missing_tool", {})

    assert all(
        not result.success for result in (missing, missing_directory, directory_read, invalid, unknown)
    )
    assert "does not exist" in missing.error
    assert "does not exist" in missing_directory.error
    assert "not a file" in directory_read.error
    assert "invalid types" in invalid.error
    assert unknown.error == "Unknown tool."


def test_dispatcher_converts_internal_tool_exceptions_to_results(tmp_path, monkeypatch) -> None:
    dispatcher = make_dispatcher(tmp_path)

    def broken_handler(arguments: object):
        raise RuntimeError("broken handler")

    monkeypatch.setitem(dispatcher._handlers, "list_files", broken_handler)
    result = dispatcher.execute("list_files", {"path": "."})

    assert result.success is False
    assert result.tool == "list_files"
    assert "Tool execution failed" in result.error


def test_workspace_rejects_traversal_and_absolute_paths(tmp_path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside", encoding="utf-8")
    inside = tmp_path / "inside.txt"
    inside.write_text("inside", encoding="utf-8")
    dispatcher = make_dispatcher(tmp_path)

    traversal = dispatcher.execute("read_file", {"path": "../" + outside.name})
    absolute = dispatcher.execute("read_file", {"path": str(inside)})
    drive_relative = dispatcher.execute("read_file", {"path": "C:outside.txt"})

    assert traversal.success is False
    assert "escapes the workspace" in traversal.error
    assert absolute.success is False
    assert "relative" in absolute.error
    assert drive_relative.success is False
    assert "relative" in drive_relative.error


def test_workspace_rejects_external_symbolic_links(tmp_path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        if os.name != "nt":
            pytest.skip(f"symbolic links are unavailable in this environment: {error}")
        junction = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True,
            text=True,
            check=False,
        )
        if junction.returncode != 0:
            pytest.skip(f"symbolic links and junctions are unavailable: {junction.stderr}")

    dispatcher = make_dispatcher(tmp_path)
    results = [
        dispatcher.execute("read_file", {"path": "link/secret.txt"}),
        dispatcher.execute("write_file", {"path": "link/new.txt", "content": "no"}),
        dispatcher.execute("list_files", {"path": "link"}),
    ]

    assert all(result.success is False for result in results)
    assert all("escapes the workspace" in result.error for result in results)
    assert not (outside / "new.txt").exists()


def test_tool_output_and_errors_are_truncated(tmp_path) -> None:
    (tmp_path / "long.txt").write_text("x" * 100, encoding="utf-8")
    dispatcher = make_dispatcher(tmp_path, max_output_chars=40)

    content = dispatcher.execute("read_file", {"path": "long.txt"}).result["content"]
    error = dispatcher.execute("read_file", {"path": "x", "unexpected_" + "x" * 100: "x"}).error

    assert len(content) == 40
    assert content.endswith(TRUNCATION_SUFFIX)
    assert len(error) == 40
    assert error.endswith(TRUNCATION_SUFFIX)
    assert truncate_output("x" * 100, 40) == content


def test_run_command_captures_success_failure_and_timeout(tmp_path) -> None:
    dispatcher = make_dispatcher(tmp_path)
    success = dispatcher.execute(
        "run_command",
        {"program": sys.executable, "args": ["-c", "import sys; print('out'); print('err', file=sys.stderr)"]},
    )
    failed = dispatcher.execute(
        "run_command", {"program": sys.executable, "args": ["-c", "import sys; sys.exit(3)"]}
    )
    timed_out = make_dispatcher(tmp_path, command_timeout_seconds=0.05).execute(
        "run_command", {"program": sys.executable, "args": ["-c", "import time; time.sleep(1)"]}
    )

    assert success.success is True
    assert success.result == {"stdout": "out\n", "stderr": "err\n", "returncode": 0, "timed_out": False}
    assert failed.success is False
    assert failed.result["returncode"] == 3
    assert timed_out.success is False
    assert timed_out.result["timed_out"] is True


def test_verification_commands_include_structured_feedback(tmp_path) -> None:
    dispatcher = make_dispatcher(tmp_path)
    result = dispatcher.execute(
        "run_command", {"program": sys.executable, "args": ["-m", "pytest", "-q"]}
    )

    assert result.result["verification"]["passed"] is False
    assert result.result["verification"]["category"] in {"assertion_failed", "command_failed"}


def test_non_verification_commands_keep_existing_result_shape(tmp_path) -> None:
    dispatcher = make_dispatcher(tmp_path)
    result = dispatcher.execute(
        "run_command", {"program": sys.executable, "args": ["-c", "print('ok')"]}
    )

    assert result.result == {"stdout": "ok\n", "stderr": "", "returncode": 0, "timed_out": False}


def test_run_command_output_is_truncated(tmp_path) -> None:
    dispatcher = make_dispatcher(tmp_path, max_output_chars=40)

    result = dispatcher.execute(
        "run_command", {"program": sys.executable, "args": ["-c", "print('x' * 100)"]}
    )

    assert result.success is True
    assert len(result.result["stdout"]) == 40
    assert result.result["stdout"].endswith(TRUNCATION_SUFFIX)


def test_truncated_output_can_be_read_by_id_without_path_access(tmp_path) -> None:
    (tmp_path / "long.txt").write_text("header\n" + "x" * 200, encoding="utf-8")
    dispatcher = make_dispatcher(tmp_path, max_output_chars=40)

    result = dispatcher.execute("read_file", {"path": "long.txt"})
    output_id = result.result["output_id"]

    full = dispatcher.execute("read_output", {"output_id": output_id})
    invalid = dispatcher.execute("read_output", {"output_id": "../../long.txt"})
    assert full.success is True
    assert len(full.result["content"]) == len("header\n" + "x" * 200)
    assert invalid.success is False
    assert "Unknown output ID" in invalid.error


def test_run_command_uses_shell_false_workspace_and_sanitized_environment(tmp_path, monkeypatch) -> None:
    dispatcher = make_dispatcher(tmp_path)
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setenv("AGENT_API_KEY", "")
    monkeypatch.setattr("coding_agent.tools.subprocess.run", fake_run)

    result = dispatcher.execute("run_command", {"program": "program", "args": ["arg"]})

    assert result.success is True
    assert captured["command"] == ["program", "arg"]
    assert captured["shell"] is False
    assert captured["cwd"] == tmp_path.resolve()
    assert "AGENT_API_KEY" not in captured["env"]


def test_run_command_removes_model_environment_from_real_child_process(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_API_KEY", "")
    dispatcher = make_dispatcher(tmp_path)

    result = dispatcher.execute(
        "run_command",
        {
            "program": sys.executable,
            "args": ["-c", "import os; print(os.getenv('AGENT_API_KEY') is None)"],
        },
    )

    assert result.success is True
    assert result.result["stdout"] == "True\n"
