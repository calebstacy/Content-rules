On the notice surface, the title field must contain no more than 50 NFC-normalized Unicode code points.
When the instance fact notice.variant equals legal_disclosure, the notice title field must contain no more than 80 NFC-normalized Unicode code points.
The notice.variant fact is an instance-level string whose allowed values are standard and legal_disclosure.
The notice-context provider observes notice.variant from the notice component variant for each notice instance; only this observed provider mapping is accepted for deterministic applicability.
Under decision EXAMPLE-LEGAL-TITLE-PRECEDENCE, notice-title-legal-limit supersedes notice-title-general-limit when both rules apply.
For this illustrative specimen, Content standards owner records the complete rule set as adopted under decision EXAMPLE-RULESET-ADOPTION.
If notice.variant is missing, comes from an unaccepted provider or basis, or has conflicting accepted assertions, applicability requires review rather than an assumed value.
