Coding Agent - Phase 1

This repository contains the first phase of a Python CLI coding agent.

Requirements: Python 3.11 or newer.

Install dependencies:
  python -m pip install -r requirements.txt
  python -m pip install -e .

Run the CLI:
  python -m coding_agent "Describe a programming task"

Configuration variables for later phases are AGENT_API_KEY, AGENT_BASE_URL,
and AGENT_MODEL. Put real values in an untracked .env file or the process
environment. Do not commit credentials.

Phase 1 does not call a model, read or write task files, or execute commands.
