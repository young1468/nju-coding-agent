"""Command-line entry point for the coding agent."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .agent import CodingAgent
from .client import LLMClientError, OpenAICompatibleClient
from .config import ConfigurationError, Settings
from .session import SessionStore
from .tools import ToolDispatcher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal coding agent CLI")
    parser.add_argument("task", help="Programming task for the agent")
    parser.add_argument(
        "--workspace", type=Path, default=Path.cwd(),
        help="Existing directory where local tools may operate (default: current directory)",
    )
    parser.add_argument(
        "--session", type=Path,
        help="Optional JSONL session file. Existing files are resumed.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        client = OpenAICompatibleClient.from_settings(Settings.from_env())
    except ConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    except LLMClientError as error:
        print(f"Model client error: {error}", file=sys.stderr)
        return 1

    try:
        dispatcher = ToolDispatcher(args.workspace)
    except ValueError as error:
        print(f"Workspace error: {error}", file=sys.stderr)
        return 2

    print(f"Task:\n{args.task}\n")
    print(f"Workspace:\n{dispatcher.workspace}\n")
    session_store = SessionStore(args.session, dispatcher.workspace) if args.session else None
    if session_store is not None:
        print(f"Session:\n{session_store.path}\n")
    print("Starting agent...\n")
    result = CodingAgent(client, dispatcher, logger=print, session_store=session_store).run(args.task)
    if result.status == "completed":
        print(f"\nFinal Answer:\n{result.answer}")
        return 0
    print(f"Agent stopped ({result.status}): {result.answer}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())