from __future__ import annotations

from coding_agent.agent import SYSTEM_MESSAGE
from coding_agent.client import AssistantResponse
import json

import pytest

from coding_agent.agent import MAX_STEPS
from coding_agent.gui import GuiSettings, GuiSettingsStore, ProgressState, _execute_plan_task, _generate_title, _refine_plan_task, _validate_settings, format_progress, new_session_path, progress_from_logs
from coding_agent.session import SessionStore


def test_gui_settings_round_trip_and_new_session_path(tmp_path) -> None:
    path = tmp_path / ".coding-agent-gui.json"
    settings = GuiSettings(workspace="workspace", sessions_directory="sessions", mode="review", max_context_chars=100, recent_context_chars=50, max_steps=20, memory_enabled=False, memory_context_chars=800)
    store = GuiSettingsStore(path)
    store.save(settings)
    assert store.load() == settings
    created = new_session_path(tmp_path / "sessions")
    assert created.parent == tmp_path / "sessions"
    assert created.suffix == ".jsonl"


def test_gui_settings_loads_default_tool_step_limit_from_legacy_file(tmp_path) -> None:
    path = tmp_path / ".coding-agent-gui.json"
    path.write_text(json.dumps({"workspace": "workspace", "sessions_directory": "sessions"}), encoding="utf-8")

    loaded = GuiSettingsStore(path).load()
    assert loaded.max_steps == MAX_STEPS
    assert loaded.memory_enabled is True
    assert loaded.memory_context_chars > 0


def test_gui_settings_rejects_invalid_tool_step_limit() -> None:
    with pytest.raises(ValueError, match="Maximum tool interaction steps"):
        _validate_settings(GuiSettings(max_steps=0))


def test_gui_settings_rejects_invalid_memory_budget() -> None:
    with pytest.raises(ValueError, match="Context budgets"):
        _validate_settings(GuiSettings(memory_context_chars=0))


def test_progress_state_parses_steps_phases_and_compactions() -> None:
    state = progress_from_logs([
        "[Agent Step 1] Requesting model",
        "[Agent Step 1] Tool: run_command",
        "Context compacted into a structured summary.",
        "Context overflow detected; compacted history and retrying.",
    ], max_steps=24)

    assert state == ProgressState("Retrying after context overflow", 1, 1, "Running")
    assert "Step: 1/24" in format_progress(state, 24)
    assert "Compactions: 1" in format_progress(state, 24)


def test_progress_state_recovers_completed_history() -> None:
    state = progress_from_logs(["[Agent Step 2] Assistant: final answer"])

    assert state.phase == "Completed"
    assert state.status == "Completed"


def test_new_session_path_can_initialize_a_resumable_session(tmp_path) -> None:
    workspace = tmp_path / "workspace"; workspace.mkdir()
    path = new_session_path(tmp_path / "sessions")
    store = SessionStore(path, workspace)
    store.initialize([{"role": "system", "content": SYSTEM_MESSAGE}])

    assert store.load_messages() == [{"role": "system", "content": SYSTEM_MESSAGE}]


class TitleClient:
    def __init__(self, response):
        self.response = response

    def complete(self, messages, tools=None):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_title_generation_uses_model_and_falls_back_without_breaking_run() -> None:
    generated = _generate_title(TitleClient(AssistantResponse("修复计算器加法逻辑", [])), "修复计算器", "测试已通过")
    fallback = _generate_title(TitleClient(RuntimeError("offline")), "Fix the calculator implementation", "done")

    assert generated == "修复计算器加法逻辑"
    assert fallback == "Fix the calculator implementation"


def test_plan_refinement_and_execution_prompts_include_user_context() -> None:
    revised = _refine_plan_task("1. Read app.py", "Also preserve the public API")
    execution = _execute_plan_task("Fix the failing test", "1. Update app.py\n2. Run pytest")

    assert "Read app.py" in revised and "preserve the public API" in revised
    assert "Fix the failing test" in execution and "Run pytest" in execution
