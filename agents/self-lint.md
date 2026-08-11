# Self-lint loop for any agent

Use this loop when creating or revising content governed by a supplied Content Rules rule set.

Before returning final content:

1. Put the current draft into the supplied or approved `content-artifact/1` mapping at `<ARTIFACT_PATH>`. Do not invent a field or surface mapping.
2. Run:

   ```text
   python "<KIT_ROOT>/scripts/run_checks.py" check --source-root "<PROJECT_ROOT>" --rules "<RULES_PATH>" --input "<ARTIFACT_PATH>" --receipt "<RECEIPT_PATH>" --force
   ```

3. Read the exit code and receipt.
4. On exit `1`, revise only the generated content fields identified by exact failures. Do not change the rule set, standards source, checker code, artifact mapping, or receipt. Run the same command again.
5. On exit `0`, return the final content and attach the passing receipt.
6. On exit `3`, stop the loop. Return the current content and receipt, and name every `REVIEW` or `NOT_APPLICABLE` result. Do not describe the result as passing.
7. On exit `2`, stop the loop and report the invalid rules, source, artifact, output path, or invocation. Do not revise content to conceal a configuration error.

Run at most five attempts. If exact failures remain after the fifth attempt, stop and return the last receipt with the unresolved failures.

The routing instruction makes the loop available to an agent. If the check is mandatory, the host workflow, hook, or CI job must require a current receipt before it accepts the work.
