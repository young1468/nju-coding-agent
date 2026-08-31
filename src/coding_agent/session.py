"""Local JSONL session storage and bounded request-context construction."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import math

MAX_CONTEXT_CHARS = 48_000
RECENT_CONTEXT_CHARS = 24_000
DEFAULT_RESERVE_TOKENS = 2_048
SESSION_VERSION = 1


@dataclass(frozen=True)
class SessionSummary:
    path: Path
    workspace: str | None
    title: str
    preview: str
    message_count: int
    updated_at: datetime
    recoverable: bool
    error: str | None = None
    stored_title: str | None = None
    logs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompactionState:
    summary: str
    first_kept_index: int
    tokens_before: int
    read_files: tuple[str, ...] = ()
    modified_files: tuple[str, ...] = ()

class SessionError(RuntimeError):
    """Raised when a local session cannot be created, loaded, or updated."""

class SessionStore:
    """Append-only, workspace-bound JSONL storage for one conversation."""
    def __init__(self, path: Path, workspace: Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.workspace = Path(workspace).resolve()
    def exists(self) -> bool:
        return self.path.exists()
    def initialize(self, messages: list[dict[str, Any]]) -> None:
        if self.path.exists():
            raise SessionError(f"Session file already exists: {self.path}")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("x", encoding="utf-8") as handle:
                self._write(handle, {"type": "session", "version": SESSION_VERSION, "workspace": str(self.workspace), "created_at": _timestamp()})
                for message in messages:
                    self._write(handle, self._entry(message))
        except OSError as error:
            raise SessionError(f"Could not create session file: {self.path}") from error
    def append_message(self, message: dict[str, Any]) -> None:
        if not self.path.is_file():
            raise SessionError(f"Session file does not exist: {self.path}")
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                self._write(handle, self._entry(message))
        except OSError as error:
            raise SessionError(f"Could not update session file: {self.path}") from error
    def load_messages(self) -> list[dict[str, Any]]:
        entries = self._load_entries()
        messages: list[dict[str, Any]] = []
        for entry in entries[1:]:
            if entry.get("type") in {"title", "log", "compaction"}:
                continue
            if entry.get("type") != "message":
                raise SessionError("Session file contains an invalid entry.")
            message = entry.get("message")
            if not isinstance(message, dict) or not isinstance(message.get("role"), str):
                raise SessionError("Session file contains an invalid message.")
            messages.append(message)
        return messages

    def load_title(self) -> str | None:
        for entry in self._load_entries()[1:]:
            if entry.get("type") == "title" and isinstance(entry.get("title"), str):
                return entry["title"]
        return None

    def load_logs(self) -> list[str]:
        return [
            entry["content"]
            for entry in self._load_entries()[1:]
            if entry.get("type") == "log" and isinstance(entry.get("content"), str)
        ]

    def load_compaction(self) -> CompactionState | None:
        latest: CompactionState | None = None
        for entry in self._load_entries()[1:]:
            if entry.get("type") != "compaction":
                continue
            if not isinstance(entry.get("summary"), str) or not isinstance(entry.get("first_kept_index"), int):
                continue
            try:
                tokens_before = int(entry.get("tokens_before", 0) or 0)
            except (TypeError, ValueError):
                tokens_before = 0
            latest = CompactionState(
                summary=entry["summary"],
                first_kept_index=max(0, entry["first_kept_index"]),
                tokens_before=tokens_before,
                read_files=tuple(item for item in entry.get("read_files", []) if isinstance(item, str)),
                modified_files=tuple(item for item in entry.get("modified_files", []) if isinstance(item, str)),
            )
        return latest

    def append_compaction(self, state: CompactionState) -> None:
        self._append_metadata({
            "type": "compaction",
            "summary": state.summary,
            "first_kept_index": state.first_kept_index,
            "tokens_before": state.tokens_before,
            "read_files": list(state.read_files),
            "modified_files": list(state.modified_files),
        })

    def set_title(self, title: str) -> None:
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Session title must be a non-empty string.")
        self._append_metadata({"type": "title", "title": title.strip()})

    def append_log(self, content: str) -> None:
        if not isinstance(content, str):
            raise ValueError("Session log must be a string.")
        self._append_metadata({"type": "log", "content": content})

    def _load_entries(self) -> list[dict[str, Any]]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise SessionError(f"Could not read session file: {self.path}") from error
        if not lines:
            raise SessionError("Session file is empty.")
        entries = [self._parse(line, index + 1) for index, line in enumerate(lines)]
        header = entries[0]
        if header.get("type") != "session":
            raise SessionError("Session file has an invalid header.")
        if header.get("version") != SESSION_VERSION:
            raise SessionError("Session file has an unsupported version.")
        if header.get("workspace") != str(self.workspace):
            raise SessionError("Session workspace does not match the requested workspace.")
        return entries

    def _append_metadata(self, entry: dict[str, Any]) -> None:
        if not self.path.is_file():
            raise SessionError(f"Session file does not exist: {self.path}")
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                self._write(handle, entry)
        except OSError as error:
            raise SessionError(f"Could not update session file: {self.path}") from error
    @staticmethod
    def _entry(message: dict[str, Any]) -> dict[str, Any]:
        return {"type": "message", "message": message, "timestamp": _timestamp()}
    @staticmethod
    def _write(handle: Any, entry: dict[str, Any]) -> None:
        handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    @staticmethod
    def _parse(line: str, number: int) -> dict[str, Any]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise SessionError(f"Session file contains invalid JSON on line {number}.") from error
        if not isinstance(value, dict):
            raise SessionError(f"Session file contains an invalid entry on line {number}.")
        return value

def build_model_messages(
    history: list[dict[str, Any]],
    max_context_chars: int = MAX_CONTEXT_CHARS,
    recent_context_chars: int = RECENT_CONTEXT_CHARS,
    compaction: CompactionState | None = None,
    reserve_tokens: int = 0,
) -> list[dict[str, Any]]:
    """Build a bounded request view; complete local history remains untouched."""
    if max_context_chars < 1 or recent_context_chars < 1 or reserve_tokens < 0:
        raise ValueError("Context limits must be positive.")
    if compaction is not None:
        summary = {"role": "system", "content": "[Compaction summary]\n" + compaction.summary}
        system_end = next((index for index, message in enumerate(history) if message.get("role") != "system"), len(history))
        start = min(max(0, compaction.first_kept_index + max(0, system_end - 1)), len(history))
        base = history[:system_end] + [summary] + history[start:]
        if len(base) < len(history) or _size(base) <= max_context_chars:
            history = base
    if _size(history) <= max_context_chars:
        return deepcopy(history)
    systems = [message for message in history if message.get("role") == "system"]
    groups = _groups([message for message in history if message.get("role") != "system"])
    selected: set[int] = set()
    used = 0
    budget = min(max_context_chars, recent_context_chars)
    if reserve_tokens:
        budget = max(1, budget - reserve_tokens * 4)
    latest_user = next((index for index in range(len(groups) - 1, -1, -1) if any(message.get("role") == "user" for message in groups[index])), None)
    if latest_user is not None:
        latest_group = groups[latest_user]
        if _size(latest_group) > budget and len(latest_group) == 1:
            latest_group = [_fit_message(latest_group[0], budget)]
            groups[latest_user] = latest_group
        selected.add(latest_user)
        used += _size(latest_group)
    for index in range(len(groups) - 1, -1, -1):
        if index in selected:
            continue
        group_size = _size(groups[index])
        if used + group_size <= budget:
            selected.add(index)
            used += group_size
    retained = [message for index, group in enumerate(groups) if index in selected for message in group]
    omitted = len([message for group in groups for message in group]) - len(retained)
    notice = {"role": "system", "content": f"[Context notice: {omitted} earlier message(s) were omitted to fit the context budget. Retained messages contain the newest task state and tool results.]"}
    return deepcopy(systems) + [notice] + deepcopy(retained)


def inspect_session(path: Path, preview_chars: int = 100) -> SessionSummary:
    """Read session metadata for display without attempting to resume it."""
    path = Path(path)
    updated_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    try:
        entries = [SessionStore._parse(line, index + 1) for index, line in enumerate(path.read_text(encoding="utf-8").splitlines())]
        if not entries:
            raise SessionError("Session file is empty.")
        header = entries[0]
        if header.get("type") != "session" or header.get("version") != SESSION_VERSION:
            raise SessionError("Session file has an invalid or unsupported header.")
        workspace = header.get("workspace")
        if not isinstance(workspace, str) or not workspace:
            raise SessionError("Session file is missing its workspace.")
        messages = []
        title: str | None = None
        logs: list[str] = []
        for entry in entries[1:]:
            entry_type = entry.get("type")
            if entry_type == "title":
                if isinstance(entry.get("title"), str):
                    title = entry["title"]
                continue
            if entry_type == "log":
                if isinstance(entry.get("content"), str):
                    logs.append(entry["content"])
                continue
            if entry_type == "compaction":
                continue
            message = entry.get("message") if entry_type == "message" else None
            if not isinstance(message, dict) or not isinstance(message.get("role"), str):
                raise SessionError("Session file contains an invalid message.")
            messages.append(message)
        text_messages = [message["content"].strip() for message in messages if isinstance(message.get("content"), str) and message["content"].strip()]
        user_messages = [message["content"].strip() for message in messages if message.get("role") == "user" and isinstance(message.get("content"), str) and message["content"].strip()]
        fallback_title = _summary_text(user_messages[0], preview_chars) if user_messages else "Empty session"
        preview = _summary_text(text_messages[-1], preview_chars) if text_messages else "No messages"
        return SessionSummary(path, workspace, title or fallback_title, preview, len(messages), updated_at, True, None, title, tuple(logs))
    except (OSError, SessionError) as error:
        return SessionSummary(path, None, "Unreadable session", str(error), 0, updated_at, False, str(error))


def list_session_summaries(directory: Path) -> list[SessionSummary]:
    """List only direct JSONL children, newest first."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(
        (inspect_session(path) for path in directory.iterdir() if path.is_file() and path.suffix == ".jsonl"),
        key=lambda summary: summary.updated_at,
        reverse=True,
    )


def delete_session_file(path: Path, directory: Path) -> None:
    """Permanently delete one direct JSONL child of the configured directory."""
    session_directory = Path(directory).expanduser().resolve()
    candidate = Path(path).expanduser().resolve(strict=False)
    if candidate.parent != session_directory or candidate.suffix != ".jsonl":
        raise SessionError("Only a direct .jsonl file in the session directory can be deleted.")
    if not candidate.is_file():
        raise SessionError("Session file does not exist.")
    try:
        candidate.unlink()
    except OSError as error:
        raise SessionError(f"Could not delete session file: {candidate}") from error

def _groups(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    index = 0
    while index < len(messages):
        if messages[index].get("role") == "assistant" and messages[index].get("tool_calls"):
            end = index + 1
            while end < len(messages) and messages[end].get("role") == "tool":
                end += 1
            groups.append(messages[index:end])
            index = end
        else:
            groups.append([messages[index]])
            index += 1
    return groups

def _size(messages: list[dict[str, Any]]) -> int:
    return len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")))


def _fit_message(message: dict[str, Any], budget: int) -> dict[str, Any]:
    content = message.get("content")
    if not isinstance(content, str):
        return deepcopy(message)
    marker = "\n[message truncated]"
    shortened = dict(message)
    low, high = 0, len(content)
    while low < high:
        mid = (low + high + 1) // 2
        shortened["content"] = content[:mid] + marker
        if _size([shortened]) <= budget:
            low = mid
        else:
            high = mid - 1
    shortened["content"] = content[:low] + marker
    return shortened


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Conservatively estimate tokens without adding a tokenizer dependency."""
    text = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
    ascii_count = sum(1 for char in text if ord(char) < 128)
    non_ascii_count = len(text) - ascii_count
    return math.ceil(ascii_count / 4) + non_ascii_count


def compact_messages(
    history: list[dict[str, Any]],
    max_context_chars: int,
    recent_context_chars: int,
    reserve_tokens: int = DEFAULT_RESERVE_TOKENS,
) -> tuple[list[dict[str, Any]], int] | None:
    """Select an old prefix for summarization and return it with its cut index."""
    if estimate_tokens(history) <= max(1, max_context_chars // 4) - reserve_tokens:
        return None
    groups = _groups([message for message in history if message.get("role") != "system"])
    if len(groups) < 2:
        return None
    keep_budget = max(1, recent_context_chars // 4)
    used = 0
    cut_group = len(groups) - 1
    for index in range(len(groups) - 1, -1, -1):
        size = estimate_tokens(groups[index])
        if used + size > keep_budget and index < len(groups) - 1:
            cut_group = index + 1
            break
        used += size
    if cut_group < len(groups) and groups[cut_group][0].get("role") == "assistant" and cut_group > 0:
        cut_group -= 1
    kept_count = sum(len(group) for group in groups[cut_group:])
    first_kept = len(history) - kept_count
    if first_kept <= 1 or first_kept >= len(history):
        return None
    return history[1:first_kept], first_kept

def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _summary_text(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."
