# Contextual title limits specimen

This specimen shows one title-length decision changing by instance context without using rule order or an implicit priority.

- `artifact.pass.json` contains a 60-code-point legal-disclosure title. Both title rules are potentially relevant, the accepted `notice.variant` assertion makes the 80-code-point rule applicable, and the recorded edge selects it over the 50-code-point rule.
- `artifact.fail.json` contains the same 60-code-point title with `notice.variant` set to `standard`. The legal rule is not applicable, so the general 50-code-point rule fails.
- `artifact.review-missing.json` omits `notice.variant`. The runtime cannot know whether the potential 80-code-point winner applies, so it reviews rather than enforcing the general rule alone.
- `artifact.review-conflict.json` supplies two accepted assertions with different values. The runtime records a fact conflict and reviews rather than choosing one assertion.

The fact mapping is intentionally narrow: `notice.variant` is an instance-level string, its only allowed values are `standard` and `legal_disclosure`, and only an `observed` assertion from `notice-context` is accepted. In a real integration, a trusted host-controlled adapter—not the writing agent—must supply that assertion; this local example does not authenticate the provider name. The self-linting agent may revise the title field; it must not change these assertions or their provenance to obtain a different rule.

## Authority boundary

The adoption and precedence decisions are illustrative records, not authenticated authority. The runtime verifies the bytes and quoted lines in `guidance.md`, and the receipts bind the rule set and artifact it evaluated. The receipt also preserves the exact precedence edge and source reference used for the selection. It does not prove that “Content standards owner” made either decision, that `notice-context` supplied the fact, that either claim is current, or that an organization should block a release. A real host workflow must control the adopted file, construct the facts, and decide consequences.
