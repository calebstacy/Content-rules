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

## Contextual rule set

Use `schema_version: content-rule-set/2` only when applicability changes according to product facts or when executable rules can compete. V2 keeps the v1 metadata, sources, scopes, checker parameters, and source references, then adds:

- `fact_definitions`: organization-defined IDs with a level, scalar type, optional allowed vocabulary, and exact accepted provenance sources
- `applies_when`: a flat `all` list using `equals`, `not_equals`, or `one_of`, plus source references for the applicability claim
- `conflict_groups`: named decisions whose member rules cannot silently co-apply
- `supersession`: explicit, source-cited edges between competing rules

Fact types are string, Boolean, or bounded integer. Values are never coerced. `true`, `1`, and `"true"` are different values.

An omitted `applies_when` means the rule is unconditional within its surface scope. Each rule may use at most one condition per fact. A missing, inferred, unaccepted, or conflicting fact never means false; it produces `REVIEW`. Because `all` is conjunction, one definitively false leaf can still establish that the rule does not apply even if another leaf is unresolved.

Conflict groups resolve separately for each content instance. A single true member runs. If multiple members are true, one recorded adopted rule must transitively supersede every competitor. Proposed edges are inactive. An unresolved possible member blocks the group rather than allowing a general rule to run while its exception is unknown.

These decision references record configured adoption and precedence. The runtime does not authenticate the owner or decision.

The published JSON Schemas check document shape, field types, and local bounds. The CLI remains the acceptance check because it also verifies relationships and whole-document limits that the schemas do not express, such as `line_end >= line_start` and the total number of fact assertions across every instance.

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

## Contextual artifact

Use `schema_version: content-artifact/2` with a v2 rule set. It adds `facts` at the artifact level and on every instance:

```json
{
  "schema_version": "content-artifact/2",
  "facts": [],
  "instances": [
    {
      "id": "notice-01",
      "surface": "account-notice",
      "fields": {
        "title": "A disclosure title"
      },
      "facts": [
        {
          "id": "notice-variant-01",
          "fact": "notice.variant",
          "value": "legal_disclosure",
          "provenance": {
            "basis": "observed",
            "provider": "notice-context",
            "ref": "component.variant"
          }
        }
      ]
    }
  ]
}
```

Facts are assertions, not bare truth values. Each has a stable assertion ID and provenance. Artifact-level assertions may satisfy only definitions whose level is `artifact`; instance assertions may satisfy only `instance` definitions. There is no implicit override. Multiple accepted assertions with the same value agree; different accepted values produce `REVIEW`.

`observed`, `declared`, and `derived` describe how the provider says it obtained the value. `inferred` is reserved for a model or heuristic and never activates a deterministic rule. The rule set must name both the accepted basis and exact provider. These are caller-supplied claims, not authenticated identities; a trusted host-controlled adapter must construct the artifact.

## Candidate inventory

`candidates.json` is an agent-authored audit surface, not runtime policy. Each source unit should preserve:

- Exact quote and line range
- Guidance type
- Automation status
- Proposed checker, when one exists
- Reason for the classification

If a term rule lacks case or whole-versus-substring behavior, or a character rule lacks a compatible counting unit, classify it as needing a human decision and omit it from `rules.json`. Do not let a runnable proposal hide an unstated mechanic.

See `examples/workspace-deletion/candidates.json`.

Use `content-rule-candidates/2` when a guidance unit depends on contextual facts or competes with another proposed rule. In addition to the v1 inventory, preserve the required fact definitions, whether a provider mapping is confirmed or missing, the competing rule IDs, and whether precedence is unresolved, proposed, or merely recorded as adopted. Do not label configured metadata as authenticated authority.

## Receipt

The runner emits `content-rule-receipt/1` JSON containing:

- Tool version
- Rule-set and artifact file hashes
- Canonical parsed-data hashes
- Recorded authority state
- Aggregate counts and status
- Per-rule status, source references, and minimal evidence

The receipt adds no timestamp, machine-absolute input path, model output, or checked-artifact excerpt. It does include configured source quotes, terms and replacements, field and surface names, owner and decision references. Treat it as potentially sensitive. The calling workflow—not the receipt—decides consequences.

The runtime reads and hashes each rules file, artifact, and source from one bounded byte buffer. Receipt output is rejected when it targets any of those inputs, including when `--force` is present.

V2 runs emit `content-rule-receipt/2`. It preserves the same hashes and result statuses, then records per-instance applicability, assertion IDs, provenance basis and provider, hashes of provenance references and fact values, unaccepted evidence, conflict-group decisions, selected rules, superseded rules, and unresolved competing rules. It does not copy raw fact values or raw provenance references into the receipt. These unsalted hashes are integrity bindings, not confidentiality; low-entropy values can be guessed.

Configured precedence is emitted once in `precedence_evidence`, including each edge's decision reference and verified source references. A configured-precedence resolution points to the exact edge IDs it used, including every edge in a transitive winning path.

Applicability states are `CONDITION_TRUE`, `CONDITION_FALSE`, `UNKNOWN_FACT`, `FACT_CONFLICT`, `RULE_CONFLICT`, and `SUPERSEDED`. These are reasons inside the trace, not new check-result statuses. Final rule results remain `PASS`, `FAIL`, `REVIEW`, or `NOT_APPLICABLE`.
