"""Local JSONL session storage and bounded request-context construction."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

MAX_CONTEXT_CHARS = 48_000
RECENT_CONTEXT_CHARS = 24_000
SESSION_VERSION = 1

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
        messages: list[dict[str, Any]] = []
        for entry in entries[1:]:
            if entry.get("type") != "message":
                raise SessionError("Session file contains an invalid entry.")
            message = entry.get("message")
            if not isinstance(message, dict) or not isinstance(message.get("role"), str):
                raise SessionError("Session file contains an invalid message.")
            messages.append(message)
        return messages
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

def build_model_messages(history: list[dict[str, Any]], max_context_chars: int = MAX_CONTEXT_CHARS, recent_context_chars: int = RECENT_CONTEXT_CHARS) -> list[dict[str, Any]]:
    """Build a bounded request view; complete local history remains untouched."""
    if max_context_chars < 1 or recent_context_chars < 1:
        raise ValueError("Context limits must be positive.")
    if _size(history) <= max_context_chars:
        return deepcopy(history)
    systems = [message for message in history if message.get("role") == "system"]
    groups = _groups([message for message in history if message.get("role") != "system"])
    selected: set[int] = set()
    used = 0
    budget = min(max_context_chars, recent_context_chars)
    latest_user = next((index for index in range(len(groups) - 1, -1, -1) if any(message.get("role") == "user" for message in groups[index])), None)
    if latest_user is not None:
        selected.add(latest_user)
        used += _size(groups[latest_user])
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

def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")