from coding_agent.feedback import classify_command_feedback, is_verification_command


def test_classifies_success_and_common_verification_failures() -> None:
    assert classify_command_feedback("pytest", ["-q"], 0).category == "passed"
    assert classify_command_feedback("pytest", ["-q"], 1, stdout="1 failed, 2 passed").category == "assertion_failed"
    assert classify_command_feedback("python", ["-m", "pytest"], 1, stderr="SyntaxError: invalid syntax").category == "syntax_error"
    assert classify_command_feedback("python", ["-m", "pytest"], 1, stderr="ModuleNotFoundError: No module named x").category == "import_error"
    assert classify_command_feedback("pytest", ["-q"], None, timed_out=True).category == "timeout"
    assert classify_command_feedback("pytest", ["-q"], 1, stderr="command not found").category == "command_not_found"
    assert classify_command_feedback("pytest", ["-q"], 3, stderr="unexpected failure").category == "command_failed"
    assert classify_command_feedback("pytest", ["-q"], None).category == "unknown_failure"


def test_verification_detection_is_conservative() -> None:
    assert is_verification_command("python", ["-m", "pytest", "-q"])
    assert is_verification_command("ruff", ["check", "."])
    assert not is_verification_command("python", ["-c", "print('hello')"])
