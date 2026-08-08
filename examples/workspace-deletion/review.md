# Ingestion review

## Proposed exact checks

- Title maximum: 50 Unicode code points after NFC normalization.
- Banned terms: `blacklist` and `whitelist`, explicitly matched as whole terms without case sensitivity.
- Preferred terminology: explicitly match the whole term `project` without case sensitivity and identify `workspace` as the configured replacement.
- Required fields: title, body, and action label must exist and contain text.

## REVIEW

> Sound calm and helpful.

This needs judgment. The source does not define an observable predicate for calmness or helpfulness, and this kit will not invent one.

## Assumptions refused

- The terminology check does not claim that `workspace` must appear when neither `workspace` nor `project` appears.
- The character check does not claim the title will fit visually inside a component.
- The required-fields check does not claim the field values are useful or accurate.
- These rules are still proposed. A passing test does not adopt them or decide what a failure should do.
