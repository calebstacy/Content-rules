# Agent routing

For a finished workspace-deletion notice, run this check after replacing the bracketed absolute paths:

```text
python "<KIT_ROOT>/scripts/run_checks.py" check --source-root "<PROJECT_ROOT>" --rules "<PROJECT_ROOT>/rules/workspace-deletion.json" --input "<artifact.json>" --receipt "<receipt.json>"
```

Attach the receipt to the review. Do not treat `REVIEW` or `NOT_APPLICABLE` as `PASS`.

This file routes the agent to the check. An authorized workflow must guarantee the command runs when the check is mandatory.
