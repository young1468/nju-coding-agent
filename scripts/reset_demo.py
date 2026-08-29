"""Restore the intentionally broken source file used by the coding-agent demo."""

from pathlib import Path

BUGGY_CALCULATOR = '''"""A deliberately faulty calculator implementation for the coding-agent demo."""


def add(left: int, right: int) -> int:
    return left - right
'''


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "demo_workspace" / "calculator.py"
    target.write_text(BUGGY_CALCULATOR, encoding="utf-8")
    print(f"Reset demo source: {target}")


if __name__ == "__main__":
    main()
