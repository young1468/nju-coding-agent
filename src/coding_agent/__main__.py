"""Command-line entry point for the coding agent."""

from __future__ import annotations

import argparse

from .config import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal coding agent CLI")
    parser.add_argument("task", help="Programming task for the agent")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    Settings.from_env()

    print(f"Task: {args.task}")
    print("Phase 1 initialized. Agent execution is not implemented yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
