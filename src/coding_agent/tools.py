"""Local workspace tools and their safe dispatcher."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
from typing import Any

MAX_OUTPUT_CHARS = 12_000
COMMAND_TIMEOUT_SECONDS = 30
TRUNCATION_SUFFIX = "\n... [truncated]"
MODEL_ENVIRONMENT_NAMES = ("AGENT_API_KEY", "AGENT_BASE_URL", "AGENT_MODEL")


@dataclass(frozen=True)
class ToolResult:
    """A JSON-serializable result from one local tool invocation."""

    success: bool
    tool: str
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


def truncate_output(text: str, max_length: int = MAX_OUTPUT_CHARS) -> str:
    """Limit text sent to the model while retaining a clear truncation marker."""

    if max_length < len(TRUNCATION_SUFFIX):
        raise ValueError("max_length is too small for the truncation marker")
    if len(text) <= max_length:
        return text
    return text[: max_length - len(TRUNCATION_SUFFIX)] + TRUNCATION_SUFFIX


class ToolDispatcher:
    """Validate and execute the four local tools within one workspace."""

    def __init__(
        self,
        workspace: Path,
        max_output_chars: int = MAX_OUTPUT_CHARS,
        command_timeout_seconds: float = COMMAND_TIMEOUT_SECONDS,
    ) -> None:
        if max_output_chars < len(TRUNCATION_SUFFIX):
            raise ValueError("max_output_chars is too small")
        if command_timeout_seconds <= 0:
            raise ValueError("command_timeout_seconds must be positive")

        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ValueError("workspace must be an existing directory")
        self._max_output_chars = max_output_chars
        self._command_timeout_seconds = command_timeout_seconds
        self._handlers: dict[str, Callable[[Mapping[str, Any]], ToolResult]] = {
            "list_files": self._list_files,
            "read_file": self._read_file,
            "write_file": self._write_file,
            "run_command": self._run_command,
        }

    def execute(self, tool_name: object, arguments: object) -> ToolResult:
        if not isinstance(tool_name, str):
            return self._error("unknown", "Tool name must be a string.")
        handler = self._handlers.get(tool_name)
        if handler is None:
            return self._error(tool_name, "Unknown tool.")
        if not isinstance(arguments, Mapping):
            return self._error(tool_name, "Tool arguments must be a JSON object.")

        try:
            return handler(arguments)
        except Exception as error:
            return self._error(tool_name, f"Tool execution failed: {error}")

    def _list_files(self, arguments: Mapping[str, Any]) -> ToolResult:
        error = self._validate_keys("list_files", arguments, {"path"})
        if error is not None:
            return error
        path = self._workspace_path(arguments["path"])
        if not path.exists():
            return self._error("list_files", "Path does not exist.")
        if not path.is_dir():
            return self._error("list_files", "Path is not a directory.")

        entries = []
        for entry in sorted(path.iterdir(), key=lambda item: item.name.lower()):
            kind = "symlink" if entry.is_symlink() else "directory" if entry.is_dir() else "file"
            entries.append(f"[{kind}] {entry.name}")
        return self._success("list_files", {"content": self._truncate("\n".join(entries))})

    def _read_file(self, arguments: Mapping[str, Any]) -> ToolResult:
        error = self._validate_keys("read_file", arguments, {"path"})
        if error is not None:
            return error
        path = self._workspace_path(arguments["path"])
        if not path.exists():
            return self._error("read_file", "File does not exist.")
        if not path.is_file():
            return self._error("read_file", "Path is not a file.")

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return self._error("read_file", "File is not valid UTF-8 text.")
        return self._success("read_file", {"content": self._truncate(content)})

    def _write_file(self, arguments: Mapping[str, Any]) -> ToolResult:
        error = self._validate_keys("write_file", arguments, {"path", "content"})
        if error is not None:
            return error
        content = arguments["content"]
        if not isinstance(content, str):
            return self._error("write_file", "Argument 'content' must be a string.")

        path = self._workspace_path(arguments["path"])
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path = self._ensure_within_workspace(path.resolve(strict=False))
            path.write_text(content, encoding="utf-8")
        except OSError as error:
            return self._error("write_file", f"Unable to write file: {error}")
        return self._success(
            "write_file",
            {"path": str(path.relative_to(self.workspace)), "bytes_written": len(content.encode("utf-8"))},
        )

    def _run_command(self, arguments: Mapping[str, Any]) -> ToolResult:
        error = self._validate_keys("run_command", arguments, {"program", "args"})
        if error is not None:
            return error
        program = arguments["program"]
        args = arguments["args"]
        if not isinstance(program, str) or not program:
            return self._error("run_command", "Argument 'program' must be a non-empty string.")
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            return self._error("run_command", "Argument 'args' must be an array of strings.")

        environment = os.environ.copy()
        for name in MODEL_ENVIRONMENT_NAMES:
            environment.pop(name, None)
        try:
            completed = subprocess.run(
                [program, *args],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                shell=False,
                timeout=self._command_timeout_seconds,
                env=environment,
                check=False,
            )
        except FileNotFoundError:
            return self._error("run_command", f"Program not found: {program}")
        except subprocess.TimeoutExpired as error:
            return ToolResult(
                success=False,
                tool="run_command",
                result={
                    "stdout": self._truncate(_text_output(error.stdout)),
                    "stderr": self._truncate(_text_output(error.stderr)),
                    "returncode": None,
                    "timed_out": True,
                },
                error=self._truncate(
                    f"Command timed out after {self._command_timeout_seconds} seconds."
                ),
            )

        result = {
            "stdout": self._truncate(_text_output(completed.stdout)),
            "stderr": self._truncate(_text_output(completed.stderr)),
            "returncode": completed.returncode,
            "timed_out": False,
        }
        if completed.returncode != 0:
            return ToolResult(
                success=False,
                tool="run_command",
                result=result,
                error=self._truncate(f"Command exited with code {completed.returncode}."),
            )
        return self._success("run_command", result)

    def _workspace_path(self, raw_path: object) -> Path:
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError("Argument 'path' must be a non-empty string.")
        candidate_path = Path(raw_path)
        windows_path = PureWindowsPath(raw_path)
        if (
            candidate_path.is_absolute()
            or windows_path.is_absolute()
            or windows_path.drive
            or raw_path.startswith(("/", "\\"))
        ):
            raise ValueError("Path must be relative to the workspace.")
        return self._ensure_within_workspace((self.workspace / candidate_path).resolve(strict=False))

    def _ensure_within_workspace(self, path: Path) -> Path:
        try:
            path.relative_to(self.workspace)
        except ValueError as error:
            raise ValueError("Path escapes the workspace.") from error
        return path

    def _validate_keys(
        self, tool: str, arguments: Mapping[str, Any], required: set[str]
    ) -> ToolResult | None:
        received = set(arguments)
        missing = required - received
        unexpected = received - required
        if missing:
            return self._error(tool, "Missing required arguments: " + ", ".join(sorted(missing)))
        if unexpected:
            return self._error(tool, "Unexpected arguments: " + ", ".join(sorted(unexpected)))
        if not all(isinstance(arguments[name], str) for name in required if name != "args"):
            return self._error(tool, "Tool arguments have invalid types.")
        return None

    def _success(self, tool: str, result: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, tool=tool, result=result)

    def _error(self, tool: str, message: str) -> ToolResult:
        return ToolResult(success=False, tool=tool, error=self._truncate(message))

    def _truncate(self, text: str) -> str:
        return truncate_output(text, self._max_output_chars)


def _text_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value
