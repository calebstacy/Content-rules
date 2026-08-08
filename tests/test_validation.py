from __future__ import annotations

import unittest

from tests.helpers import artifact, rule, rule_set
from content_rules.common import RuleError, validate_artifact, validate_rule_set


class ValidationTests(unittest.TestCase):
    def test_valid_rule_set_and_empty_rule_set_are_accepted(self) -> None:
        validate_rule_set(rule_set(rule("banned_terms")))
        validate_rule_set(rule_set())

    def test_unknown_fields_and_duplicate_rule_ids_are_rejected(self) -> None:
        unknown = rule_set(rule("banned_terms"))
        unknown["rules"][0]["typo"] = True
        with self.assertRaises(RuleError):
            validate_rule_set(unknown)
        duplicate = rule_set(rule("banned_terms", rule_id="same"), rule("character_limit", rule_id="same"))
        with self.assertRaises(RuleError):
            validate_rule_set(duplicate)

    def test_invalid_parameters_are_rejected(self) -> None:
        empty_term = rule_set(rule("banned_terms"))
        empty_term["rules"][0]["params"]["terms"] = [""]
        with self.assertRaises(RuleError):
            validate_rule_set(empty_term)
        negative_limit = rule_set(rule("character_limit"))
        negative_limit["rules"][0]["params"]["maximum"] = -1
        with self.assertRaises(RuleError):
            validate_rule_set(negative_limit)

    def test_document_size_limits_are_enforced_before_evaluation(self) -> None:
        too_many_sources = rule_set()
        source = rule_set(rule("character_limit"))["sources"][0]
        too_many_sources["sources"] = [
            {**source, "id": f"source-{index}"}
            for index in range(51)
        ]
        with self.assertRaisesRegex(RuleError, "sources exceeds"):
            validate_rule_set(too_many_sources)

        too_many_rules = rule_set(*(rule("character_limit", rule_id=f"limit-{index}") for index in range(201)))
        with self.assertRaisesRegex(RuleError, "rules exceeds"):
            validate_rule_set(too_many_rules)

        too_many_refs = rule_set(rule("character_limit"))
        reference = too_many_refs["rules"][0]["source_refs"][0]
        too_many_refs["rules"][0]["source_refs"] = [dict(reference) for _ in range(21)]
        with self.assertRaisesRegex(RuleError, "source_refs exceeds"):
            validate_rule_set(too_many_refs)

        term_rules = []
        for rule_index in range(6):
            configured = rule("banned_terms", rule_id=f"terms-{rule_index}")
            configured["params"]["terms"] = [f"term-{rule_index}-{term_index}" for term_index in range(100)]
            term_rules.append(configured)
        with self.assertRaisesRegex(RuleError, "term entries exceed"):
            validate_rule_set(rule_set(*term_rules))

    def test_conflicting_terminology_mappings_are_rejected(self) -> None:
        first = rule("required_terminology", rule_id="first")
        second = rule("required_terminology", rule_id="second")
        second["params"]["preferred"] = "authenticate"
        with self.assertRaises(RuleError):
            validate_rule_set(rule_set(first, second))

    def test_case_sensitive_terminology_may_govern_case_only(self) -> None:
        configured = rule("required_terminology")
        configured["params"].update(
            {
                "preferred": "Sign in",
                "instead_of": ["Sign In"],
                "case_sensitive": True,
            }
        )
        validate_rule_set(rule_set(configured))

    def test_unresolved_template_values_are_rejected(self) -> None:
        unresolved = rule_set(rule("banned_terms"))
        unresolved["rules"][0]["params"]["case_sensitive"] = "__REPLACE_ME__"
        with self.assertRaisesRegex(RuleError, "template"):
            validate_rule_set(unresolved)
        zero_hash = rule_set(rule("banned_terms"))
        zero_hash["sources"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(RuleError, "template"):
            validate_rule_set(zero_hash)

    def test_natural_replace_with_language_is_valid_source_evidence(self) -> None:
        configured = rule_set(rule("required_terminology"))
        configured["rules"][0]["description"] = "Replace with the approved account term."
        configured["rules"][0]["source_refs"][0]["quote"] = "Replace with the approved account term."
        validate_rule_set(configured)

    def test_source_paths_cannot_escape_or_be_remote(self) -> None:
        escaped = rule_set(rule("banned_terms"))
        escaped["sources"][0]["path"] = "../secret.md"
        with self.assertRaises(RuleError):
            validate_rule_set(escaped)
        remote = rule_set(rule("banned_terms"))
        remote["sources"][0]["path"] = "https://example.com/guide"
        with self.assertRaises(RuleError):
            validate_rule_set(remote)
        drive_path = rule_set(rule("banned_terms"))
        drive_path["sources"][0]["path"] = "C:/standards/guidance.md"
        with self.assertRaises(RuleError):
            validate_rule_set(drive_path)

    def test_adopted_metadata_requires_owner_and_decision_reference(self) -> None:
        adopted = rule_set(rule("banned_terms"))
        adopted["rule_set"]["status"] = "adopted"
        with self.assertRaises(RuleError):
            validate_rule_set(adopted)
        adopted["rule_set"]["owner"] = "Content standards owner"
        adopted["rule_set"]["decision_ref"] = "DECISION-42"
        validate_rule_set(adopted)

    def test_artifact_rejects_duplicate_ids_and_unknown_fields(self) -> None:
        duplicate = artifact({"title": "Ready"})
        duplicate["instances"].append(duplicate["instances"][0].copy())
        with self.assertRaises(RuleError):
            validate_artifact(duplicate)
        unknown = artifact({"title": "Ready"})
        unknown["unexpected"] = True
        with self.assertRaises(RuleError):
            validate_artifact(unknown)

        too_many_instances = artifact({"title": "Ready"})
        too_many_instances["instances"] = [
            {"id": f"notice-{index}", "surface": "test", "fields": {"title": "Ready"}}
            for index in range(1001)
        ]
        with self.assertRaisesRegex(RuleError, "instances exceeds"):
            validate_artifact(too_many_instances)


if __name__ == "__main__":
    unittest.main()
