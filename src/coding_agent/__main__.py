"""Command-line entry point for the coding agent."""

from __future__ import annotations

import argparse
import sys

from .agent import CodingAgent
from .client import LLMClientError, OpenAICompatibleClient
from .config import ConfigurationError, Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal coding agent CLI")
    parser.add_argument("task", help="Programming task for the agent")
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

    result = CodingAgent(client, logger=print).run(args.task)
    if result.status == "completed":
        print(f"Final answer: {result.answer}")
        return 0

    print(f"Agent stopped ({result.status}): {result.answer}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
