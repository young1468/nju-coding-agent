"""Tkinter desktop workspace for the local coding agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import queue
import re
import threading
from tkinter import END, BOTH, X, filedialog, messagebox, ttk
import tkinter as tk
from uuid import uuid4

from .agent import MAX_STEPS, CodingAgent, MODE_TOOL_NAMES, SYSTEM_MESSAGE
from .client import LLMClientError, OpenAICompatibleClient
from .config import ConfigurationError, Settings
from .memory import DEFAULT_MEMORY_CONTEXT_CHARS, MemoryManager, MemoryStore
from .session import DEFAULT_RESERVE_TOKENS, MAX_CONTEXT_CHARS, RECENT_CONTEXT_CHARS, SessionError, SessionStore, SessionSummary, delete_session_file, list_session_summaries
from .tools import ToolDispatcher


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = PROJECT_ROOT / ".coding-agent-gui.json"
TITLE_SYSTEM = "Generate one concise session title in the same language as the task. Return only the title, on one line, no quotes, no prefix, and no more than 40 characters."


@dataclass
class GuiSettings:
    workspace: str = str(PROJECT_ROOT)
    sessions_directory: str = str(PROJECT_ROOT / ".sessions")
    mode: str = "auto"
    max_context_chars: int = MAX_CONTEXT_CHARS
    recent_context_chars: int = RECENT_CONTEXT_CHARS
    reserve_tokens: int = DEFAULT_RESERVE_TOKENS
    max_steps: int = MAX_STEPS
    memory_enabled: bool = True
    memory_context_chars: int = DEFAULT_MEMORY_CONTEXT_CHARS
    selected_session: str | None = None


class GuiSettingsStore:
    def __init__(self, path: Path = SETTINGS_PATH) -> None:
        self.path = Path(path)

    def load(self) -> GuiSettings:
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
            settings = GuiSettings(**{name: values[name] for name in GuiSettings.__dataclass_fields__ if name in values})
            _validate_settings(settings)
            return settings
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return GuiSettings()

    def save(self, settings: GuiSettings) -> None:
        _validate_settings(settings)
        self.path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class ProgressState:
    phase: str = "Idle"
    step: int = 0
    compactions: int = 0
    status: str = "Idle"


def progress_from_logs(lines: list[str], max_steps: int = MAX_STEPS) -> ProgressState:
    """Derive a compact, human-readable status from the existing agent logs."""
    phase = "Idle"
    status = "Idle"
    step = 0
    compactions = 0
    for line in lines:
        match = re.search(r"\[Agent Step (\d+)\]", line)
        if match:
            step = max(step, int(match.group(1)))
        if "Context compacted" in line:
            phase = "Context summarized"
            compactions += 1
        elif "Context overflow" in line:
            phase = "Retrying after context overflow"
        elif "Tool: read_file" in line or "Tool: list_files" in line:
            phase = "Reading files"
        elif "Tool: write_file" in line:
            phase = "Writing files"
        elif "Tool: run_command" in line:
            phase = "Running verification"
        elif "Requesting model" in line:
            phase = "Analyzing project"
        elif "final answer" in line.lower():
            phase = "Completed"
            status = "Completed"
    if lines and status == "Idle":
        status = "Running"
    if phase == "Completed":
        status = "Completed"
    return ProgressState(phase=phase, step=step, compactions=compactions, status=status)


def format_progress(state: ProgressState, max_steps: int = MAX_STEPS) -> str:
    return f"Phase: {state.phase} | Step: {state.step}/{max_steps} | Compactions: {state.compactions} | Status: {state.status}"


def new_session_path(directory: Path) -> Path:
    return Path(directory) / f"session-{uuid4().hex}.jsonl"


def _first_user_task(messages: list[dict[str, object]]) -> str | None:
    for message in messages:
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            content = " ".join(message["content"].split())
            if content:
                return content
    return None


def _fallback_title(task: str) -> str:
    first_line = next((line.strip() for line in task.splitlines() if line.strip()), "Coding task")
    first_line = first_line.rstrip("。.!！?？")
    return first_line if len(first_line) <= 40 else first_line[:37].rstrip() + "..."


def _generate_title(client: object, task: str, answer: str) -> str:
    fallback = _fallback_title(task)
    try:
        response = client.complete(
            [
                {"role": "system", "content": TITLE_SYSTEM},
                {"role": "user", "content": f"Task:\n{task}\n\nFinal answer:\n{answer}"},
            ],
            tools=None,
        )
        if isinstance(response.content, str):
            title = next((line.strip() for line in response.content.splitlines() if line.strip()), "")
            if title.lower().startswith("title:"):
                title = title.split(":", 1)[1].strip()
            title = title.strip("\"'` ")
            if title:
                return title if len(title) <= 40 else title[:37].rstrip() + "..."
    except Exception:
        pass
    return fallback


def _detailed_message_logs(messages: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    for message in messages:
        role = message.get("role")
        if role == "assistant" and message.get("tool_calls"):
            for call in message["tool_calls"]:
                if isinstance(call, dict):
                    function = call.get("function", {})
                    if isinstance(function, dict):
                        lines.append(f"assistant tool call {function.get('name', 'unknown')}: {function.get('arguments', '{}')}")
        elif role == "tool":
            lines.append(f"tool result: {message.get('content', '')}")
    return lines


def _tool_message_name(content: object) -> str:
    if isinstance(content, str):
        try:
            value = json.loads(content)
            if isinstance(value, dict) and isinstance(value.get("tool"), str):
                return value["tool"]
        except json.JSONDecodeError:
            pass
    return "completed"


def _refine_plan_task(plan: str, feedback: str) -> str:
    return f"Revise the implementation plan below according to the user's feedback. Inspect files as needed, then return only the revised plan.\n\nCurrent plan:\n{plan}\n\nUser feedback:\n{feedback}"


def _execute_plan_task(original_task: str, plan: str) -> str:
    return f"Execute the following approved implementation plan for the original task. Follow it carefully, inspect files as needed, make the required changes, and run relevant verification.\n\nOriginal task:\n{original_task}\n\nApproved plan:\n{plan}"


class CodingAgentApp:
    def __init__(self, root: tk.Tk, settings_store: GuiSettingsStore | None = None) -> None:
        self.root = root
        self.store = settings_store or GuiSettingsStore()
        self.settings = self.store.load()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running = False
        self.summaries: list[SessionSummary] = []
        self.log_lines: list[str] = []
        self.log_window: tk.Toplevel | None = None
        self.log_text: tk.Text | None = None
        self.plan_origin_task = ""
        self.executing_plan = False
        self.progress_var = tk.StringVar(value=format_progress(ProgressState(), self.settings.max_steps))
        self._build()
        self.refresh_sessions()
        self.root.after(100, self._drain_events)

    def _build(self) -> None:
        self.root.title("Coding Agent")
        self.root.geometry("1200x720")
        outer = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        outer.pack(fill=BOTH, expand=True, padx=8, pady=8)
        history = ttk.Frame(outer, padding=8)
        center = ttk.Frame(outer, padding=8)
        controls = ttk.Frame(outer, padding=8)
        outer.add(history, weight=1); outer.add(center, weight=3); outer.add(controls, weight=2)
        ttk.Label(history, text="Historical sessions").pack(anchor="w")
        ttk.Button(history, text="New session", command=self.new_session).pack(fill=X, pady=(6, 2))
        ttk.Button(history, text="Refresh", command=self.refresh_sessions).pack(fill=X)
        self.delete_button = ttk.Button(history, text="Delete session", command=self.delete_session)
        self.delete_button.pack(fill=X, pady=(2, 0))
        self.session_list = tk.Listbox(history, exportselection=False)
        self.session_list.pack(fill=BOTH, expand=True, pady=8)
        self.session_list.bind("<<ListboxSelect>>", self.select_session)
        ttk.Label(center, text="Conversation").pack(anchor="w")
        ttk.Label(center, textvariable=self.progress_var).pack(anchor="w", pady=(2, 2))
        self.output = tk.Text(center, wrap="word", state="disabled")
        self.output.pack(fill=BOTH, expand=True, pady=(6, 4))
        ttk.Label(center, text="Plan (editable in Plan mode)").pack(anchor="w")
        self.plan_text = tk.Text(center, height=8, wrap="word", state="disabled")
        self.plan_text.pack(fill=X, pady=(4, 0))
        ttk.Label(controls, text="Task / plan feedback").pack(anchor="w")
        self.task = tk.Text(controls, height=10, wrap="word")
        self.task.pack(fill=X, pady=(2, 8))
        self.workspace = self._entry(controls, "Workspace", self.settings.workspace)
        self.session = self._entry(controls, "Session file", self.settings.selected_session or "")
        ttk.Label(controls, text="Mode").pack(anchor="w", pady=(8, 2))
        self.mode = tk.StringVar(value=self.settings.mode)
        ttk.Combobox(controls, textvariable=self.mode, values=list(MODE_TOOL_NAMES), state="readonly").pack(fill=X)
        ttk.Button(controls, text="Settings", command=self.open_settings).pack(fill=X, pady=(12, 2))
        ttk.Button(controls, text="View logs", command=self.show_logs).pack(fill=X, pady=(2, 2))
        ttk.Button(controls, text="View memory", command=self.view_memory).pack(fill=X, pady=(2, 2))
        self.refine_button = ttk.Button(controls, text="Refine plan", command=self.refine_plan, state="disabled")
        self.refine_button.pack(fill=X, pady=(2, 2))
        self.execute_plan_button = ttk.Button(controls, text="Execute plan", command=self.execute_plan, state="disabled")
        self.execute_plan_button.pack(fill=X, pady=(2, 2))
        self.run_button = ttk.Button(controls, text="Run agent", command=self.run_agent)
        self.run_button.pack(fill=X)

    def _entry(self, parent: ttk.Frame, label: str, value: str) -> ttk.Entry:
        ttk.Label(parent, text=label).pack(anchor="w", pady=(8, 2))
        entry = ttk.Entry(parent); entry.insert(0, value); entry.pack(fill=X)
        return entry

    def _append_main(self, text: str) -> None:
        self.output.configure(state="normal"); self.output.insert(END, text + "\n"); self.output.see(END); self.output.configure(state="disabled")

    def refresh_sessions(self) -> None:
        self.summaries = list_session_summaries(Path(self.settings.sessions_directory))
        self.session_list.delete(0, END)
        for summary in self.summaries:
            prefix = "" if summary.recoverable else "[unreadable] "
            updated = summary.updated_at.astimezone().strftime("%Y-%m-%d %H:%M")
            details = summary.workspace or summary.error or "Unknown workspace"
            self.session_list.insert(
                END,
                f"{prefix}{summary.title}\n{summary.preview}\n{details}\n{updated} · {summary.message_count} messages",
            )

    def new_session(self) -> None:
        path = new_session_path(Path(self.settings.sessions_directory))
        try:
            SessionStore(path, Path(self.workspace.get().strip())).initialize(
                [{"role": "system", "content": SYSTEM_MESSAGE}]
            )
        except (SessionError, ValueError) as error:
            messagebox.showerror("New session", str(error))
            return
        self.session.delete(0, END); self.session.insert(0, str(path))
        self.task.delete("1.0", END); self._append_main(f"New session created: {path.name}")
        self.log_lines = []; self.plan_origin_task = ""; self.executing_plan = False; self._set_plan(""); self._set_plan_actions(False)
        self._update_progress()
        self._save_settings(); self.refresh_sessions()

    def delete_session(self) -> None:
        if self.running:
            return
        selection = self.session_list.curselection()
        if not selection:
            messagebox.showinfo("Delete session", "Select a session to delete first.")
            return
        summary = self.summaries[selection[0]]
        if not messagebox.askyesno(
            "Delete session",
            f"Permanently delete this session and all of its messages and logs?\n\n{summary.path}\n\nThis cannot be undone in the GUI.",
        ):
            return
        try:
            delete_session_file(summary.path, Path(self.settings.sessions_directory))
        except SessionError as error:
            messagebox.showerror("Delete session", str(error))
            return
        current = self.session.get().strip()
        current_path = Path(current).expanduser().resolve(strict=False) if current else None
        if current_path == summary.path.resolve(strict=False):
            self.session.delete(0, END)
            self.output.configure(state="normal"); self.output.delete("1.0", END); self.output.configure(state="disabled")
            self.log_lines = []; self.plan_origin_task = ""; self.executing_plan = False
            self._set_plan(""); self.session_list.selection_clear(0, END)
            self.settings.selected_session = None
            self._update_progress()
        self.refresh_sessions()
        self._save_settings()

    def select_session(self, _event: object) -> None:
        selection = self.session_list.curselection()
        if not selection:
            return
        summary = self.summaries[selection[0]]
        if not summary.recoverable:
            messagebox.showerror("Session", summary.error or "This session cannot be restored.")
            return
        self.workspace.delete(0, END); self.workspace.insert(0, summary.workspace or "")
        self.session.delete(0, END); self.session.insert(0, str(summary.path))
        try:
            session_store = SessionStore(summary.path, Path(summary.workspace or ""))
            messages = session_store.load_messages()
            self.log_lines = session_store.load_logs()
        except SessionError as error:
            messagebox.showerror("Session", str(error))
            return
        self._show_conversation(messages)
        last_plan = next((message.get("content") for message in reversed(messages) if message.get("role") == "assistant" and isinstance(message.get("content"), str)), "")
        self._set_plan(last_plan if self.mode.get() == "plan" else "")
        self.plan_origin_task = _first_user_task(messages) or ""
        self._set_plan_actions(bool(self.mode.get() == "plan" and last_plan))
        self._render_logs()
        self._update_progress()
        self._save_settings()

    def run_agent(self) -> None:
        if self.running:
            return
        task = self.task.get("1.0", END).strip()
        workspace = self.workspace.get().strip()
        session = self.session.get().strip() or str(new_session_path(Path(self.settings.sessions_directory)))
        if not task or not workspace:
            messagebox.showerror("Run agent", "Task and workspace are required.")
            return
        if self.mode.get() == "plan":
            self.plan_origin_task = task
            self._set_plan("")
            self._set_plan_actions(False)
        self.session.delete(0, END); self.session.insert(0, session)
        self._start_run(task, workspace, session, self.mode.get(), "plan" if self.mode.get() == "plan" else "normal")

    def _start_run(self, task: str, workspace: str, session: str, mode: str, purpose: str) -> None:
        existing_logs: list[str] = []
        session_path = Path(session).expanduser()
        if session_path.is_file():
            try:
                existing_logs = SessionStore(session_path, Path(workspace)).load_logs()
            except SessionError:
                existing_logs = []
        self.running = True; self.log_lines = existing_logs; self._render_logs()
        self._update_progress(status="Running")
        self.run_button.configure(state="disabled"); self._append_main(f"Task:\n{task}"); self._append_main("Starting agent...")
        self.refine_button.configure(state="disabled"); self.execute_plan_button.configure(state="disabled")
        self.delete_button.configure(state="disabled")
        self._save_settings()
        thread = threading.Thread(target=self._run, args=(task, workspace, session, mode, purpose), daemon=True)
        thread.start()

    def refine_plan(self) -> None:
        plan = self.plan_text.get("1.0", END).strip()
        feedback = self.task.get("1.0", END).strip()
        if not plan or not feedback:
            messagebox.showerror("Refine plan", "Enter feedback in the task box and keep a generated plan.")
            return
        self._start_run(_refine_plan_task(plan, feedback), self.workspace.get().strip(), self.session.get().strip(), "plan", "plan")

    def execute_plan(self) -> None:
        plan = self.plan_text.get("1.0", END).strip()
        workspace = self.workspace.get().strip()
        session = self.session.get().strip()
        if not plan or not workspace or not session:
            messagebox.showerror("Execute plan", "A plan, workspace, and session are required.")
            return
        self.executing_plan = True
        self._start_run(_execute_plan_task(self.plan_origin_task or self.task.get("1.0", END).strip(), plan), workspace, session, "auto", "execute_plan")

    def _run(self, task: str, workspace: str, session: str, mode: str, purpose: str) -> None:
        try:
            dispatcher = ToolDispatcher(Path(workspace))
            store = SessionStore(Path(session), dispatcher.workspace)
            previous_messages = store.load_messages() if store.exists() else []
            client = OpenAICompatibleClient.from_settings(Settings.from_env())
            memory_manager = (
                MemoryManager(dispatcher.workspace, client, max_context_chars=self.settings.memory_context_chars)
                if self.settings.memory_enabled else None
            )
            runtime_logs: list[str] = []
            agent = CodingAgent(
                client, dispatcher,
                logger=lambda line: (runtime_logs.append(line), self.events.put(("log", line))), session_store=store,
                mode=mode, max_context_chars=self.settings.max_context_chars,
                recent_context_chars=self.settings.recent_context_chars,
                reserve_tokens=self.settings.reserve_tokens,
                max_steps=self.settings.max_steps,
                memory_manager=memory_manager,
            )
            result = agent.run(task)
            new_messages = result.messages[len(previous_messages):]
            for line in runtime_logs + _detailed_message_logs(new_messages):
                store.append_log(line)
            title = store.load_title()
            if result.status == "completed" and not title:
                first_task = _first_user_task(result.messages) or task
                title = _generate_title(client, first_task, result.answer)
                store.set_title(title)
            self.events.put(("done", {"answer": result.answer, "title": title, "mode": mode, "purpose": purpose, "status": result.status}))
        except (ConfigurationError, LLMClientError, SessionError, ValueError) as error:
            self.events.put(("error", str(error)))

    def _drain_events(self) -> None:
        while not self.events.empty():
            kind, value = self.events.get()
            if kind == "log":
                self.log_lines.append(str(value)); self._append_key_log(str(value)); self._update_progress(status="Running"); self._render_logs()
            elif kind == "done":
                payload = value if isinstance(value, dict) else {"answer": value}
                result_status = str(payload.get("status", "completed"))
                display_status = "Completed" if result_status == "completed" else "Stopped"
                self._finish("Final answer:\n" + str(payload.get("answer", "")), display_status)
                if payload.get("mode") == "plan" and payload.get("status") == "completed":
                    self._set_plan(str(payload.get("answer", "")))
                    self._set_plan_actions(True)
                elif payload.get("purpose") == "execute_plan":
                    self.executing_plan = False
            else: self._finish("Error:\n" + str(value), "Failed")
        self.root.after(100, self._drain_events)

    def _finish(self, text: str, status: str = "Completed") -> None:
        self._append_main(text); self.running = False; self.run_button.configure(state="normal"); self.delete_button.configure(state="normal"); self._update_progress(status=status); self.refresh_sessions()
        if not self.executing_plan and self.plan_text.get("1.0", END).strip() and self.mode.get() == "plan":
            self._set_plan_actions(True)

    def _set_plan(self, text: str) -> None:
        self.plan_text.configure(state="normal"); self.plan_text.delete("1.0", END); self.plan_text.insert("1.0", text); self.plan_text.configure(state="normal" if text else "disabled")

    def _set_plan_actions(self, enabled: bool) -> None:
        state = "normal" if enabled and not self.running else "disabled"
        self.refine_button.configure(state=state)
        self.execute_plan_button.configure(state=state)

    def _append_key_log(self, line: str) -> None:
        if "Arguments:" in line or "Result:" in line:
            return
        if "Requesting model" in line:
            self._append_main("Analyzing project...")
        elif "Tool:" in line:
            self._append_main("Using tool: " + line.split("Tool:", 1)[1].strip())
        elif "Assistant: tool call" in line:
            self._append_main("Agent is inspecting the workspace...")
        elif "Context compacted" in line:
            self._append_main("Context summarized to continue safely.")
        elif "Context overflow" in line:
            self._append_main("Context limit reached; retrying with a summary...")
        elif "final answer" in line.lower():
            self._append_main("Agent finished.")

    def _update_progress(self, status: str | None = None) -> None:
        state = progress_from_logs(self.log_lines, self.settings.max_steps)
        if status is not None:
            state = ProgressState(state.phase, state.step, state.compactions, status)
        self.progress_var.set(format_progress(state, self.settings.max_steps))

    def _show_conversation(self, messages: list[dict[str, object]]) -> None:
        self.output.configure(state="normal"); self.output.delete("1.0", END)
        for message in messages:
            role = message.get("role", "unknown")
            if role == "user":
                self.output.insert(END, f"You:\n{message.get('content') or ''}\n\n")
            elif role == "assistant" and message.get("tool_calls"):
                names = [call.get("function", {}).get("name", "unknown") for call in message["tool_calls"] if isinstance(call, dict)]
                self.output.insert(END, f"Agent: inspecting ({', '.join(names)})\n\n")
            elif role == "assistant":
                self.output.insert(END, f"Agent:\n{message.get('content') or ''}\n\n")
            elif role == "tool":
                self.output.insert(END, f"Tool completed: {_tool_message_name(message.get('content'))}\n\n")
        self.output.configure(state="disabled")

    def show_logs(self) -> None:
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.lift(); self._render_logs(); return
        self.log_window = tk.Toplevel(self.root); self.log_window.title("Agent logs"); self.log_window.geometry("760x520")
        self.log_text = tk.Text(self.log_window, wrap="word", state="disabled")
        self.log_text.pack(fill=BOTH, expand=True, padx=8, pady=8)
        self.log_window.protocol("WM_DELETE_WINDOW", self._close_logs)
        self._render_logs()

    def view_memory(self) -> None:
        try:
            store = MemoryStore(Path(self.workspace.get().strip()))
            content = (
                f"# Global memory\n\n{store.read_markdown('global')}\n"
                f"# Project memory\n\n{store.read_markdown('project')}"
            )
        except (OSError, ValueError) as error:
            messagebox.showerror("View memory", str(error), parent=self.root)
            return
        window = tk.Toplevel(self.root); window.title("Long-term memory"); window.geometry("760x520")
        text = tk.Text(window, wrap="word", state="normal"); text.pack(fill=BOTH, expand=True, padx=8, pady=8)
        text.insert("1.0", content); text.configure(state="disabled")

    def _close_logs(self) -> None:
        if self.log_window is not None:
            self.log_window.destroy()
        self.log_window = None; self.log_text = None

    def _render_logs(self) -> None:
        if self.log_text is None or self.log_window is None or not self.log_window.winfo_exists():
            return
        self.log_text.configure(state="normal"); self.log_text.delete("1.0", END)
        self.log_text.insert(END, "\n".join(self.log_lines))
        self.log_text.see(END); self.log_text.configure(state="disabled")

    def _save_settings(self) -> None:
        self.settings.workspace = self.workspace.get().strip()
        self.settings.mode = self.mode.get()
        self.settings.selected_session = self.session.get().strip() or None
        self.store.save(self.settings)

    def open_settings(self) -> None:
        dialog = tk.Toplevel(self.root); dialog.title("Settings"); dialog.transient(self.root); dialog.grab_set()
        workspace = self._settings_field(dialog, "Default workspace", self.settings.workspace)
        sessions = self._settings_field(dialog, "Session directory", self.settings.sessions_directory)
        ttk.Button(dialog, text="Choose workspace folder", command=lambda: self._choose_directory(dialog, workspace)).pack(anchor="w", padx=12, pady=(2, 6))
        ttk.Button(dialog, text="Choose session folder", command=lambda: self._choose_directory(dialog, sessions)).pack(anchor="w", padx=12, pady=(2, 6))
        max_context = self._settings_field(dialog, "Context character budget", str(self.settings.max_context_chars))
        recent_context = self._settings_field(dialog, "Recent character budget", str(self.settings.recent_context_chars))
        reserve_tokens = self._settings_field(dialog, "Response reserve tokens", str(self.settings.reserve_tokens))
        max_steps = self._settings_field(dialog, "Maximum tool interaction steps", str(self.settings.max_steps))
        memory_enabled = tk.BooleanVar(value=self.settings.memory_enabled)
        ttk.Checkbutton(dialog, text="Enable long-term memory", variable=memory_enabled).pack(anchor="w", padx=12, pady=(8, 2))
        memory_context = self._settings_field(dialog, "Memory context character budget", str(self.settings.memory_context_chars))
        ttk.Label(dialog, text="Character budgets are approximate; reserve tokens leave room for the model reply. Tool steps limit model tool-use rounds. Memory is stored locally in Markdown and a JSON index.").pack(padx=12, pady=6)
        def save() -> None:
            try:
                self.settings.workspace = workspace.get().strip(); self.settings.sessions_directory = sessions.get().strip()
                self.settings.max_context_chars = int(max_context.get()); self.settings.recent_context_chars = int(recent_context.get())
                self.settings.reserve_tokens = int(reserve_tokens.get())
                self.settings.max_steps = int(max_steps.get())
                self.settings.memory_enabled = bool(memory_enabled.get())
                self.settings.memory_context_chars = int(memory_context.get())
                _validate_settings(self.settings); self.store.save(self.settings); self.workspace.delete(0, END); self.workspace.insert(0, self.settings.workspace)
                dialog.destroy(); self.refresh_sessions()
            except ValueError as error: messagebox.showerror("Settings", str(error), parent=dialog)
        ttk.Button(dialog, text="Save", command=save).pack(padx=12, pady=12)

    def _settings_field(self, dialog: tk.Toplevel, label: str, value: str) -> ttk.Entry:
        ttk.Label(dialog, text=label).pack(anchor="w", padx=12, pady=(8, 2)); entry = ttk.Entry(dialog, width=70); entry.insert(0, value); entry.pack(fill=X, padx=12); return entry

    @staticmethod
    def _choose_directory(dialog: tk.Toplevel, entry: ttk.Entry) -> None:
        selected = filedialog.askdirectory(parent=dialog, initialdir=entry.get() or str(PROJECT_ROOT))
        if selected:
            entry.delete(0, END)
            entry.insert(0, selected)


def _validate_settings(settings: GuiSettings) -> None:
    if settings.mode not in MODE_TOOL_NAMES:
        raise ValueError("Mode must be Auto, Review, or Plan.")
    if settings.max_context_chars < 1 or settings.recent_context_chars < 1 or settings.reserve_tokens < 0 or settings.memory_context_chars < 1:
        raise ValueError("Context budgets must be positive.")
    if settings.max_steps < 1:
        raise ValueError("Maximum tool interaction steps must be at least 1.")
    if settings.recent_context_chars > settings.max_context_chars:
        raise ValueError("Recent context budget cannot exceed total context budget.")


def main() -> None:
    root = tk.Tk(); CodingAgentApp(root); root.mainloop()


if __name__ == "__main__":
    main()
