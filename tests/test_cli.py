from __future__ import annotations

import subprocess
import sys
import os


def test_cli_reports_missing_model_configuration(tmp_path) -> None:
    task = "Fix the failing tests without modifying test files"
    environment = os.environ.copy()
    for name in ("AGENT_API_KEY", "AGENT_BASE_URL", "AGENT_MODEL"):
        environment.pop(name, None)
    result = subprocess.run(
        [sys.executable, "-m", "coding_agent", task],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "Configuration error:" in result.stderr
    assert "AGENT_API_KEY" in result.stderr
