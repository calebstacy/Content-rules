# Self-lint loop for any agent

Use this loop when creating or revising content governed by a supplied Content Rules rule set.

Before returning final content:

1. Put the current draft into the supplied or approved artifact mapping at `<ARTIFACT_PATH>`. Use `content-artifact/1` with a v1 rule set and `content-artifact/2` with a v2 rule set. Do not invent a field, surface, fact, or provider mapping.
2. Run:

   ```text
   python "<KIT_ROOT>/scripts/run_checks.py" check --source-root "<PROJECT_ROOT>" --rules "<RULES_PATH>" --input "<ARTIFACT_PATH>" --receipt "<RECEIPT_PATH>" --force
   ```

3. Read the exit code and receipt.
4. On exit `1`, revise only the generated content fields identified by exact failures. Do not change the rule set, standards source, checker code, artifact mapping, v2 fact assertions, provenance, or receipt. Run the same command again.
5. On exit `0`, return the final content and attach the passing receipt.
6. On exit `3`, stop the loop. Return the current content and receipt, and name every `REVIEW` or `NOT_APPLICABLE` result. Do not describe the result as passing.
7. On exit `2`, stop the loop and report the invalid rules, source, artifact, output path, or invocation. Do not revise content to conceal a configuration error.

Run at most five attempts. If exact failures remain after the fifth attempt, stop and return the last receipt with the unresolved failures.

Writing agents must not change these assertions or their provenance to make a rule disappear, and must never claim the identity of an accepted fact provider. Missing, inferred, unaccepted, or conflicting facts are inputs for a trusted host-controlled adapter or responsible product workflow to resolve, not content for the writing agent to repair.

The routing instruction makes the loop available to an agent. If the check is mandatory, the host workflow, hook, or CI job must require a current receipt before it accepts the work.
