from __future__ import annotations

import unittest

from tests.helpers import artifact, rule
from content_rules import banned_terms


class BannedTermsTests(unittest.TestCase):
    def test_case_insensitive_whole_term_fails(self) -> None:
        active = rule("banned_terms")
        result = banned_terms.evaluate(active, artifact({"title": "LOG failed"}))
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["evidence"][0]["occurrences"], 1)

    def test_case_sensitive_rule_distinguishes_case(self) -> None:
        active = rule("banned_terms")
        active["params"]["case_sensitive"] = True
        self.assertEqual(banned_terms.evaluate(active, artifact({"title": "LOG failed"}))["status"], "PASS")

    def test_whole_term_ignores_catalog_and_log_1_but_catches_log_hyphen(self) -> None:
        active = rule("banned_terms")
        self.assertEqual(banned_terms.evaluate(active, artifact({"title": "catalog log_1"}))["status"], "PASS")
        self.assertEqual(banned_terms.evaluate(active, artifact({"title": "log-in"}))["status"], "FAIL")

    def test_substring_mode_catches_catalog(self) -> None:
        active = rule("banned_terms")
        active["params"]["match"] = "substring"
        self.assertEqual(banned_terms.evaluate(active, artifact({"title": "catalog"}))["status"], "FAIL")

    def test_occurrence_evidence_is_capped_without_changing_failure(self) -> None:
        active = rule("banned_terms")
        active["params"]["match"] = "substring"
        result = banned_terms.evaluate(active, artifact({"title": "log" * 1001}))
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["evidence"][0]["occurrences"], 1000)
        self.assertTrue(result["evidence"][0]["occurrences_capped"])

    def test_unicode_normalization_and_casefold_are_pinned(self) -> None:
        cafe = rule("banned_terms")
        cafe["params"]["terms"] = ["café"]
        self.assertEqual(banned_terms.evaluate(cafe, artifact({"title": "cafe\u0301"}))["status"], "FAIL")
        street = rule("banned_terms")
        street["params"]["terms"] = ["strasse"]
        self.assertEqual(banned_terms.evaluate(street, artifact({"title": "Straße"}))["status"], "FAIL")

    def test_scope_does_not_scan_sibling_fields(self) -> None:
        active = rule("banned_terms")
        result = banned_terms.evaluate(active, artifact({"title": "Clear", "body": "log"}))
        self.assertEqual(result["status"], "PASS")

    def test_missing_or_non_string_target_returns_review(self) -> None:
        active = rule("banned_terms")
        self.assertEqual(banned_terms.evaluate(active, artifact({"body": "Clear"}))["status"], "REVIEW")
        self.assertEqual(banned_terms.evaluate(active, artifact({"title": 42}))["status"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
