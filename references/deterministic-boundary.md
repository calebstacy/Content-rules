# Deterministic boundary

A rule belongs in executable checks only when ordinary code can determine both applicability and outcome from the supplied rule set and typed artifact.

The same defined input must produce the same result. That says nothing about whether the rule is legitimate, wise, complete, or authorized.

## Safe candidates

- Exact literal terms that must not occur, with explicit case and whole-versus-substring behavior
- Exact deprecated-to-preferred term mappings, with explicit case and whole-versus-substring behavior
- Exact maximum counts for named fields, with a counting unit supported by the checker
- Exact required fields for named surfaces, including whether empty values count as present

## Needs more information

- “Keep titles short” needs a number and a target field.
- “Avoid jargon” needs a list or another explicitly authorized predicate.
- “Use this in errors” needs a surface and field mapping.
- “Include the core benefit” needs an exact observable requirement or human review.
- “Do not use Oops” still needs case behavior and whole-versus-substring behavior.
- “No more than 36 characters” still needs a counting unit; this starter supports NFC-normalized Unicode code points.

## Needs judgment

- Clear, warm, calm, helpful, confident, concise, or human
- Appropriate, inclusive, accessible, legally compliant, safe, or on-brand as broad claims
- Whether a statement is true, useful, blameful, manipulative, or contextually right
- Whether a field’s action actually works in the product

A narrow static proxy may support one of these reviews, but the proxy must be named as the thing checked. Do not rename it as proof of the broader quality.

## Missing evidence

- Missing field for `required_fields`: `FAIL`. Absence is the predicate.
- Missing field for a text or count check: `REVIEW` evidence. The checker lacks its evidence. A separate observed violation can still make the rule `FAIL`, but the unresolved evidence remains separately counted.
- No matching surface: `NOT_APPLICABLE`. The rule did not target the supplied artifact.
- No applicable rules: `NOT_APPLICABLE`, never `PASS`.

## Authority

An agent may propose a rule. A script may prove that the configured predicate passed or failed. Neither act adopts policy.

Authorization, severity, release effect, exception handling, and waiver approval belong to an organization-owned workflow. Receipts record what ran; they do not prove entitlement or make the decision good.
