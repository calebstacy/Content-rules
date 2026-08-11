# Content Rules

[![Tests](https://github.com/calebstacy/Content-rules/actions/workflows/tests.yml/badge.svg)](https://github.com/calebstacy/Content-rules/actions/workflows/tests.yml)

Turn the rules in your style guide into checks your agents can actually run.

Content Rules helps you stop catching the same exact content mistakes by hand. Give the included skill your standards and a sample of your product content. It helps your agent identify the guidance with exact answers, prepare the rules, and test them against examples that should pass and fail.

The current kit can check:

- words and phrases you have banned;
- character limits for specific fields;
- deprecated terms and their approved replacements;
- content fields that must be present.

It can also decide **which exact rule applies in which situation**. A title can have one limit in an ordinary notice and another in a legal disclosure, for example, without asking the model to remember the exception. Content Rules uses typed, source-named facts to select the rule. If the needed fact is missing or disputed, the result is `REVIEW` rather than a guess.

The checks run separately from the agent that wrote the content. A model does not get to decide that its own answer followed the rule. The result comes back with a receipt showing which rules ran, what passed, what failed, and what still needs a person.

You do not need to write Python. The Python is already here. Your team supplies the standards, reviews the proposed rules, and decides where those rules apply.

## What you get

- **A skill for your agent:** it walks through your guidance, proposes runnable rules, and prepares test examples.
- **Four working content checks:** banned terms, character limits, preferred terminology, and required fields.
- **A self-linting loop:** the agent checks its draft, fixes exact failures, and checks again before returning the work.
- **A repeatable result:** the same content and rule produce the same answer every time.
- **A source trail:** every proposed rule points back to the guidance it came from.
- **A review queue:** tone, meaning, usefulness, and other genuine design decisions stay visible for people.
- **A path to expand:** new kinds of exact content rules can become new checkers without turning the style guide into a larger prompt.
- **Context without guesswork:** conditional rules can use explicit product facts, surface conflicts, and record why one rule was selected over another.

Content Rules does not replace your standards. It gives the enforceable parts somewhere to run.

## Make any agent self-lint

Any agent that can run a local command can use the same loop:

```text
Draft → run Content Rules → fix exact failures → run it again → return the receipt
```

The reusable instructions are in [`agents/self-lint.md`](agents/self-lint.md). They tell the agent to revise the content when a check fails without weakening the rule, changing the checker, or hiding anything that still needs review.

The loop gives the agent a reliable way to correct its own output. When a check must happen every time, put the same command in the workflow that accepts the agent's work.

## Start here

Clone the repository and open a terminal in it:

```bash
git clone https://github.com/calebstacy/Content-rules.git
cd Content-rules
```

Confirm that Python 3.10 or newer is available:

```text
python --version
```

On Windows, use `py --version` and replace `python` with `py` in the examples if that is how Python is installed.

## See it happen

The example guidance contains five instructions:

```md
- Titles can contain no more than 50 Unicode code points after NFC normalization.
- Do not use the exact whole terms “blacklist” or “whitelist” in the title, body, or action label, regardless of letter case.
- In the body, use the exact whole term “workspace” instead of “project,” regardless of letter case.
- Include a non-empty title, body, and action label.
- Sound calm and helpful.
```

The first four become proposed checks. The last remains in [`review.md`](examples/workspace-deletion/review.md), because the source gives the script no observable definition of calmness or helpfulness.

Validate the proposal:

```bash
python scripts/run_checks.py validate --rules examples/workspace-deletion/rules.json
```

Run the passing example:

```bash
python scripts/run_checks.py check --rules examples/workspace-deletion/rules.json --input examples/workspace-deletion/artifact.pass.json
```

Run the failing example:

```bash
python scripts/run_checks.py check --rules examples/workspace-deletion/rules.json --input examples/workspace-deletion/artifact.fail.json
```

That command exits `1` on purpose. Its checked-in [receipt](examples/workspace-deletion/receipt.fail.json) shows:

```text
FAIL  title-max-50
       title contains 62 Unicode code points. Maximum: 50.

FAIL  banned-list-terms
       Found “blacklist” in body.

FAIL  workspace-terminology
       Found “project” in body. Preferred term: “workspace”.

FAIL  required-notice-fields
       action_label is empty.

Aggregate: FAIL
Separate review queue: “Sound calm and helpful.”
```

The JSON receipt does not copy the checked artifact text. It does include configured source quotes, terms and replacements, field and surface names, owner and decision references, plus the minimum evidence needed to explain each result. Treat receipts as potentially sensitive when those values are proprietary.

V2 receipts include contextual assertion IDs plus hashes of provenance references and fact values, not the raw reference or value. Those unsalted hashes are integrity bindings, not secrecy: a low-entropy enum can still be guessed. Treat the receipt as potentially sensitive.

## Use it with your standards

If your agent supports `SKILL.md`, install or point it at this whole repository. The skill resolves two locations: `KIT_ROOT` is this repository, while `PROJECT_ROOT` is the workspace containing your standards and product content. Proposals belong under the project, even when the kit is installed elsewhere.

If your agent does not support skills, give it this instruction after replacing the bracketed paths:

```text
Read <KIT_ROOT>/SKILL.md and follow it. Treat <KIT_ROOT> as the checker kit
and <PROJECT_ROOT> as the product workspace. Do not assume they are the same.

Audit <PROJECT_ROOT>/my-guidance.md against
<PROJECT_ROOT>/sample-content.json.

Use only the four checkers shipped in this repository. Create a proposal,
fixtures, and a review list under <PROJECT_ROOT>/proposals/my-guidance/.

Do not edit the Python checkers. Do not invent thresholds, term lists,
field mappings, exceptions, counting units, case behavior, or whether a term
match is whole or substring.

Only propose a JSON rule when the shipped checker can return the same answer
from the defined field every time. Put guidance involving tone, meaning,
quality, missing context, or an unstated decision in REVIEW. Mark an exact
rule as unsupported when this repository has no checker for it.

Include the original source location for every proposed rule. Give every
rule at least one example that should pass and one that should fail. Validate
the proposed configuration and run every fixture.

Then show me:
1. What you proposed
2. What you left in REVIEW
3. What is unsupported
4. Every test result
5. Every assumption you refused to make

Do not move the proposal into <PROJECT_ROOT>/rules/, choose whether failures warn or
block, edit CI or hooks, create waivers, or describe the proposal as adopted.
```

The prompt starts the workflow. It is not the enforcement mechanism.

## When the rule changes with the situation

Some standards are exact but not universal:

```text
Ordinary notice title: maximum 50 code points
Legal-disclosure title: maximum 80 code points
Use the 80-character rule only when notice.variant = legal_disclosure
```

That is still deterministic—if a trusted product adapter supplies `notice.variant` through the named context provider.

Content Rules v2 represents that context as a typed assertion with an ID and provenance. The rule set defines which provider and evidence basis it accepts. Then the runtime evaluates each content instance separately:

```text
accepted legal_disclosure fact   -> select the 80-character rule
accepted standard fact           -> use the 50-character rule
missing or inferred fact         -> REVIEW
two accepted facts that disagree -> REVIEW
```

The runtime does not use numeric priority, file order, source count, or a vague “most specific rule wins” shortcut. Rules that govern the same decision form an explicit conflict group. If more than one applies, one must have a recorded supersession path over every competitor. Otherwise none of the competing checks runs and the result is `REVIEW`.

See the complete [contextual title-limit example](examples/contextual-title-limits/) and [v2 format reference](references/formats.md). Existing v1 rule sets keep their original meaning; you only need v2 when applicability itself depends on facts or competing rules.

Run the contextual passing example:

```bash
python scripts/run_checks.py check --source-root examples/contextual-title-limits --rules examples/contextual-title-limits/rules.json --input examples/contextual-title-limits/artifact.pass.json
```

Swap the input for `artifact.fail.json`, `artifact.review-missing.json`, or `artifact.review-conflict.json` to see the other three paths.

## What ships

| Starter | What it can establish | What it cannot establish |
| --- | --- | --- |
| Banned terms | A configured literal term occurred in a named field | The language is broadly inclusive or appropriate |
| Character limit | A named string exceeds an exact code-point limit | Whether it visually clips in a component |
| Preferred terminology | A configured old term occurred and has a configured replacement | Whether the concept should have been mentioned |
| Required fields | A named field exists and, when configured, contains text | Whether the value is truthful, useful, or connected to working behavior |

The Python modules are fixed. The editable surface is JSON under `templates/`, `examples/`, `proposals/`, or an organization-owned `rules/` directory.

Files under `templates/` use the reserved value `__REPLACE_ME__`. They are scaffolds, not active policy. Replace every sentinel and the zeroed source digest before validation.

## What stays in REVIEW

Keep guidance in review when it asks for tone, meaning, usefulness, clarity, legal or policy interpretation, broad accessibility compliance, factuality, or anything else the supplied fields cannot prove.

Also use review when an otherwise exact rule is missing its threshold, term list, replacement, target field, target surface, exception, counting unit, case behavior, or whole-term-versus-substring behavior. “Do not use Oops” is close to executable, but it still does not say whether `oops` or `Whoops` counts.

Prefer a missed automation opportunity over a false failure. A false negative stays visible for review. A false deterministic claim manufactures certainty.

## Where prompt.md fits

A Markdown instruction can point an agent to the check:

```md
For finished workspace-deletion notices, run:

python "<KIT_ROOT>/scripts/run_checks.py" check --source-root "<PROJECT_ROOT>" --rules "<PROJECT_ROOT>/rules/workspace-deletion.json" --input "<artifact.json>" --receipt "<receipt.json>"

Attach the receipt to the review. Do not treat REVIEW or NOT_APPLICABLE as PASS.
```

This tells the agent where the rule lives and how to run it. It does not guarantee the command ran. If the check must always happen, an authorized owner wires the same command into CI, a hook, or another required workflow step.

Do not copy the threshold into a routing `prompt.md`. The organization-owned standards source remains normative; the JSON is its executable projection, bound to an exact source hash and quote. If the source changes, this checker stops until someone reviews and updates the proposal. The routing file only points to that check.

## Who makes FAIL matter?

The checker does not.

`rule_set.status` records `proposed` or `adopted`. An adopted file must name an owner and decision reference, but this repository cannot prove that either one is legitimate. Its exit code describes the check result. A team-owned workflow decides whether that result warns, requests review, or blocks delivery.

The same boundary applies to v2 precedence and facts. A configured decision reference can explain why one rule superseded another, and a fact can name the provider that allegedly supplied it. Both are recorded claims, not authenticated authority or identity. A controlled repository, signature, or trusted host workflow must establish who was allowed to decide and must supply facts through a host-controlled adapter.

An agent can propose a configuration. Tests can prove the checker behaves as specified. Neither can authorize the rule or decide what its failure is allowed to do.

## File tree

```text
content-rules/
├── README.md
├── SKILL.md
├── schemas/
├── scripts/
│   ├── run_checks.py
│   └── content_rules/
│       ├── banned_terms.py
│       ├── character_limit.py
│       ├── required_terminology.py
│       └── required_fields.py
├── templates/
├── examples/workspace-deletion/
├── examples/contextual-title-limits/
├── proposals/
├── rules/
└── tests/
```

- Your standards remain authoritative where your organization owns them. The JSON stores a version-bound executable projection, not a replacement source of policy.
- `proposals/` contains agent-drafted configurations waiting for review.
- `rules/` is reserved for configurations adopted through the organization’s real controls.
- `scripts/` contains the tested Python the agent is not supposed to rewrite during ingestion.
- A receipt shows what ran. It is evidence, not approval.

## Exact behavior

- Inputs are typed JSON artifacts made of content instances, surfaces, and fields. The checker never guesses a field or silently scans the whole JSON document.
- V1 is the compact format for unconditional rules. V2 adds typed fact definitions, fact assertions, exact conditions, and explicit conflict groups. A v1 rule set must use a v1 artifact; a v2 rule set must use a v2 artifact.
- V2 facts are assertions, not declarations of truth. Each assertion names its provenance basis (`observed`, `declared`, `derived`, or `inferred`), provider, and evidence reference. A rule set names the exact non-inferred sources it accepts, but the local runtime does not authenticate the provider string. A trusted host-controlled adapter must construct the artifact.
- Model- or heuristic-inferred facts never activate a deterministic rule. They remain visible as unresolved context until an accepted provider supplies the fact.
- V2 conditions are deliberately small: `equals`, `not_equals`, and `one_of`, combined in a flat `all` list with at most one condition per fact. There is no regex, clock, arbitrary JSON path, nested rule language, or implicit default for missing facts.
- Conditions resolve per content instance. A rule may run on one instance, be false on another, and require review on a third in the same artifact.
- Rules in a conflict group never win by order or numeric priority. Proposed supersession is inactive. Recorded adopted supersession must be acyclic and select one rule over every active competitor; otherwise the group returns `REVIEW` and runs none of them.
- The runtime checks that artifact JSON. It does not inspect the original Figma file, codebase, CMS entry, or Markdown output. Any adapter that creates the artifact is another governed boundary and can itself be wrong; test and review that mapping separately.
- Text matching normalizes Unicode to NFC. Case-insensitive matching then uses locale-independent Unicode case folding.
- `whole` matching treats Unicode letters, numbers, and `_` as word characters. `substring` has different consequences. Configure either behavior only when the source or an authorized profile supplies that choice.
- The shipped character checker counts Unicode code points after NFC normalization. That is not bytes, rendered width, or user-perceived graphemes. For example, a joined emoji can count as several code points. A source that says only “characters” needs this counting decision before it becomes a rule.
- A missing required field is `FAIL`, because absence is what that checker measures.
- A missing field needed by another checker creates `REVIEW` evidence, because that checker lacks evidence. It never falls back to another field. If the same multi-field rule also finds an actual violation, the rule remains `FAIL` and the receipt separately counts the unresolved evidence.
- A surface with no matching content is `NOT_APPLICABLE`, not `PASS`.
- Empty rule sets are `NOT_APPLICABLE`, not proof of compliance.
- Files must be UTF-8 and no larger than 5 MB. The runtime uses only the Python standard library and makes no network calls.
- JSON is strict: duplicate keys, non-finite numbers, oversized numeric literals, and invalid Unicode surrogates stop with a structured error instead of being guessed or silently rewritten.
- One run accepts at most 50 sources, 200 rules, 20 source references per rule, 1,000 artifact instances, and 500 configured term entries. Occurrence evidence stops counting at 1,000 and marks the count as capped.
- V2 additionally accepts at most 100 fact definitions, 100 artifact-level assertions, 50 assertions per instance, 5,000 assertions overall, 20 conditions per rule, 100 conflict groups, 50 members per group, 500 supersession edges, and 10,000 matching rule-instance evaluations. Preflight stops a run if one result could exceed 1,000 evidence items or the receipt could exceed 25,000 total detail units. The final JSON receipt may not exceed 16 MB.
- Source paths resolve inside the current directory by default. Use `--source-root <project-directory>` when running elsewhere. A missing, escaping, or changed source—or a quote that does not match its cited lines—stops the check with exit `2`.
- Rules, artifacts, and sources are hashed from the same bounded bytes that were parsed. A receipt cannot replace any of those files, even with `--force`.
- This starter verifies local files only. For standards in a wiki, Figma, or another remote system, an authorized workflow must create a local UTF-8 snapshot first. The kit binds to that snapshot; it does not sync or govern the remote original.
- This is not a sandbox between mutually hostile local users. Run it in a controlled workspace when another process could replace project files during the check.
- Receipts add no timestamps or machine-absolute input paths, so the same files produce byte-identical output. Configured source quotes and identifiers can still contain sensitive organization text; v2 hashes raw fact provenance references before emitting them.

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | At least one rule applied and all applicable rules passed |
| `1` | One or more exact checks failed |
| `2` | Invalid invocation, rules, artifact, encoding, or output path |
| `3` | No failure, but REVIEW or zero applicability remains |

## Test the kit

Python 3.10 or newer is required. There are no runtime dependencies.

```bash
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
```

The tests pin Unicode behavior, scoping, missing evidence, malformed configuration, receipt determinism, output safety, and all four exit paths.

They also pin v2 fact provenance, per-instance condition selection, conflicting assertions, inactive proposed precedence, recorded adopted supersession, cycle rejection, mixed-version errors, and expansion limits.

See [MIGRATION.md](MIGRATION.md) if an existing rule genuinely needs context. You do not have to migrate an unconditional v1 rule set.

## License

[MIT](LICENSE)
