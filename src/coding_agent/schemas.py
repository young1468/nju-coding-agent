"""OpenAI-compatible definitions for the local coding tools."""

from __future__ import annotations

from typing import Any

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List the immediate contents of a workspace-relative directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 text file at a workspace-relative path.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or replace a UTF-8 text file at a workspace-relative path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a program with string arguments in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "program": {"type": "string"},
                    "args": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["program", "args"],
                "additionalProperties": False,
            },
        },
    },
]

READ_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "read_output",
        "description": "Read a previously truncated tool output by its output ID.",
        "parameters": {
            "type": "object",
            "properties": {"output_id": {"type": "string"}},
            "required": ["output_id"],
            "additionalProperties": False,
        },
    },
}
