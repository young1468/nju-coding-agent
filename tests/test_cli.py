from __future__ import annotations

import subprocess
import sys


def test_cli_accepts_a_task() -> None:
    task = "Fix the failing tests without modifying test files"
    result = subprocess.run(
        [sys.executable, "-m", "coding_agent", task],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert f"Task: {task}" in result.stdout
    assert "Phase 1 initialized" in result.stdout
    assert result.stderr == ""
