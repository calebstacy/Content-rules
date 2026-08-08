# Formats

## Rule set

Use `schema_version: content-rule-set/1`. A rule set contains:

- `rule_set`: identity plus `proposed` or `adopted` status
- `sources`: local source or approved-snapshot paths relative to the selected project root, plus SHA-256 values the runner verifies before checking content
- `rules`: fixed checker configurations with exact source references

Proposed rule sets use `null` for `owner` and `decision_ref`. Adopted rule sets must name both, but the runtime records rather than authenticates them.

Every rule contains:

- Stable lowercase `id`
- Plain-language `description`
- One shipped `check`
- Explicit `scope.surfaces` and `scope.fields`
- Checker-specific `params`
- At least one source reference with an exact quote and line range

Use the complete working example at `examples/workspace-deletion/rules.json` and the individual objects under `templates/`.

## Artifact

Use `schema_version: content-artifact/1`:

```json
{
  "schema_version": "content-artifact/1",
  "instances": [
    {
      "id": "notice-01",
      "surface": "workspace-deletion",
      "fields": {
        "title": "We couldn’t delete this workspace",
        "body": "Try again."
      }
    }
  ]
}
```

Instances represent repeated components or content objects. Required fields are evaluated per instance, so a title in one object cannot satisfy a missing title in another.

Field values used by text checkers must be strings. A non-string value remains visible as `REVIEW`; it is never silently converted to text.

## Candidate inventory

`candidates.json` is an agent-authored audit surface, not runtime policy. Each source unit should preserve:

- Exact quote and line range
- Guidance type
- Automation status
- Proposed checker, when one exists
- Reason for the classification

If a term rule lacks case or whole-versus-substring behavior, or a character rule lacks a compatible counting unit, classify it as needing a human decision and omit it from `rules.json`. Do not let a runnable proposal hide an unstated mechanic.

See `examples/workspace-deletion/candidates.json`.

## Receipt

The runner emits `content-rule-receipt/1` JSON containing:

- Tool version
- Rule-set and artifact file hashes
- Canonical parsed-data hashes
- Recorded authority state
- Aggregate counts and status
- Per-rule status, source references, and minimal evidence

The receipt includes no timestamp, absolute path, model output, or checked-artifact excerpt. It does include configured source quotes, terms and replacements, field and surface names, owner and decision references. Treat it as potentially sensitive. The calling workflow—not the receipt—decides consequences.

The runtime reads and hashes each rules file, artifact, and source from one bounded byte buffer. Receipt output is rejected when it targets any of those inputs, including when `--force` is present.
