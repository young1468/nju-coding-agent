# Calculator Demo

This isolated project intentionally contains a bug in `calculator.py` and a
failing pytest in `test_calculator.py`.

From the repository root, run the coding agent with configured model settings:

```powershell
python -m coding_agent "Fix the failing tests without modifying test files" --workspace demo_workspace
```

The agent should inspect the files, run `python -m pytest -q`, fix only the
implementation, rerun the tests, and report the result.

To restore the intentionally broken implementation after a demo run, use:

```powershell
python scripts/reset_demo.py
```
