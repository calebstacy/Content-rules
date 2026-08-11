# Moving from v1 to v2

You do not have to migrate.

`content-rule-set/1` remains the smaller, correct format for rules whose applicability is already defined by surface and field. The v2 format exists for a different job: rules that change according to typed product facts, named exceptions, or competing constraints.

## Compatibility

| Rule set | Artifact | Receipt | Result |
| --- | --- | --- | --- |
| `content-rule-set/1` | `content-artifact/1` | `content-rule-receipt/1` | Existing v1 behavior |
| `content-rule-set/2` | `content-artifact/2` | `content-rule-receipt/2` | Contextual behavior |
| v1 | v2 | Error | `INCOMPATIBLE_PROTOCOLS` |
| v2 | v1 | Error | `INCOMPATIBLE_PROTOCOLS` |

Content Rules does not silently upgrade or reinterpret an old document. The four checker modules and v1 status semantics remain unchanged.

## Use v2 when

- the same field has different exact requirements in named product states;
- a rule has an explicit exception whose applicability can be supplied as a typed fact;
- locale, jurisdiction, audience, content role, component state, flow stage, or another organization-defined fact changes the rule;
- two executable constraints can apply to the same decision and need an explicit relationship.

Do not use v2 merely to store more descriptive context. If a fact does not change applicability, keep it out of the execution contract.

## Migration steps

1. Copy the v2 templates into a new proposal. Do not overwrite an adopted v1 file.
2. Define each required fact: stable ID, artifact or instance level, scalar type, allowed vocabulary when closed, and exact accepted provenance source.
3. Identify the real, host-controlled adapter or product boundary that supplies each assertion. A writing model is not an acceptable fact authority, and the local runtime does not authenticate a caller-supplied provider name.
4. Add a source-cited `applies_when` condition to each contextual rule. V2 supports only `equals`, `not_equals`, and `one_of` in a flat `all` list, with at most one condition for each fact.
5. If executable rules compete, put them in one conflict group. Add source-cited supersession only when the source or a recorded decision establishes it.
6. Keep the proposal `proposed`. Proposed supersession is intentionally inactive.
7. Test condition true, condition false, missing fact, conflicting accepted facts, and unaccepted or inferred facts.
8. Test every conflict group with no winner and with its recorded adopted winner.
9. Have the organization’s real owner review the source, fact mapping, fixtures, and consequences before replacing any adopted configuration.

## Important boundaries

- Missing or conflicting facts produce `REVIEW`, not false.
- Inferred facts never activate deterministic rules.
- Artifact- and instance-level facts do not override one another.
- Rule order, numeric priority, source count, and “most specific wins” never resolve a conflict.
- A recorded owner, decision reference, provenance basis, or provider identity is not authenticated by this runtime.
- Receipt fact values and provenance references are hashed, not encrypted. Their hashes bind the run to the input; they do not make small vocabularies secret.
- A writing agent may revise content fields after an exact failure. It may not edit facts, provenance, mappings, rules, or precedence to make a check disappear.

See [`examples/contextual-title-limits/`](examples/contextual-title-limits/) for the complete v2 path.
