"""Deterministic classification of command verification results."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VerificationFeedback:
    passed: bool
    category: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_verification_command(program: str, args: list[str]) -> bool:
    """Return whether a command is likely to produce an objective check result."""
    executable = Path(program).name.lower()
    normalized = " ".join([executable, *args]).lower()
    return any(
        marker in normalized
        for marker in (
            "pytest",
            "python -m unittest",
            "ruff",
            "mypy",
            "pyright",
            "npm test",
            "cargo test",
            "go test",
        )
    )


def classify_command_feedback(
    program: str,
    args: list[str],
    returncode: int | None,
    stdout: str = "",
    stderr: str = "",
    timed_out: bool = False,
) -> VerificationFeedback:
    """Classify a command using deterministic process and diagnostic signals."""
    if timed_out:
        return VerificationFeedback(False, "timeout", "Verification command timed out.")

    diagnostics = f"{stdout}\n{stderr}".lower()
    if returncode == 0:
        return VerificationFeedback(True, "passed", "Verification command completed successfully.")
    if any(marker in diagnostics for marker in ("syntaxerror", "syntax error")):
        return VerificationFeedback(False, "syntax_error", "Verification failed because of a syntax error.")
    if any(marker in diagnostics for marker in ("modulenotfounderror", "importerror", "no module named")):
        return VerificationFeedback(False, "import_error", "Verification failed because an import could not be resolved.")
    if any(marker in diagnostics for marker in ("assertionerror", "assert ", " failed", "failures")):
        return VerificationFeedback(False, "assertion_failed", "Verification command failed with test assertions.")
    if any(marker in diagnostics for marker in ("not found", "not recognized", "no such file or directory")):
        return VerificationFeedback(False, "command_not_found", f"Command could not be found: {program}.")
    if returncode is not None:
        return VerificationFeedback(False, "command_failed", f"Verification command exited with code {returncode}.")
    return VerificationFeedback(False, "unknown_failure", "Verification command did not produce a conclusive result.")
