# Deterministic boundary

A rule belongs in executable checks only when ordinary code can determine both applicability and outcome from the supplied rule set and typed artifact.

The same defined input must produce the same result. That says nothing about whether the rule is legitimate, wise, complete, or authorized.

Applicability is part of the predicate. “Use this limit for legal disclosures” is executable only when a trusted host-controlled adapter supplies a typed disclosure fact from a provider the rule set explicitly accepts. The checker must not ask the writing model to decide whether its own draft is a legal disclosure or let it claim the trusted provider identity.

## Safe candidates

- Exact literal terms that must not occur, with explicit case and whole-versus-substring behavior
- Exact deprecated-to-preferred term mappings, with explicit case and whole-versus-substring behavior
- Exact maximum counts for named fields, with a counting unit supported by the checker
- Exact required fields for named surfaces, including whether empty values count as present
- Exact conditions over named scalar facts supplied by a defined product or adapter boundary
- Explicitly related competing constraints with a recorded, source-cited supersession path

## Needs more information

- “Keep titles short” needs a number and a target field.
- “Avoid jargon” needs a list or another explicitly authorized predicate.
- “Use this in errors” needs a surface and field mapping.
- “Include the core benefit” needs an exact observable requirement or human review.
- “Do not use Oops” still needs case behavior and whole-versus-substring behavior.
- “No more than 36 characters” still needs a counting unit; this starter supports NFC-normalized Unicode code points.
- “Use the longer limit for serious errors” needs an observable definition of serious, a typed fact, and a provider mapping.
- “Use the regional rule” needs a canonical locale or jurisdiction value; the checker must not infer one from the words.

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
- Missing, inferred, unaccepted, or conflicting contextual fact: `REVIEW`. Unknown context is never silently treated as false. In a multi-fact `all` condition, a separate definitively false leaf still establishes that the whole rule does not apply.
- Multiple competing rules with no single configured winner: `REVIEW`; run none of the competing checks.
- A superseded rule: `NOT_APPLICABLE` for that instance, with the selection preserved in the v2 receipt.

## Authority

An agent may propose a rule. A script may prove that the configured predicate passed or failed. Neither act adopts policy.

Authorization, severity, release effect, exception handling, and waiver approval belong to an organization-owned workflow. Receipts record what ran; they do not prove entitlement or make the decision good.

V2 `adopted`, owner, decision references, provenance bases, and provider names are recorded claims. The local runtime validates their shape and uses configured precedence; it does not authenticate the person, provider identity, repository control, signature, or decision system behind them.
