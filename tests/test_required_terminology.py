from __future__ import annotations

import unittest

from tests.helpers import artifact, rule
from content_rules import required_terminology


class RequiredTerminologyTests(unittest.TestCase):
    def test_deprecated_term_fails_and_names_replacement(self) -> None:
        active = rule("required_terminology")
        result = required_terminology.evaluate(active, artifact({"title": "Log in now"}))
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["evidence"][0]["preferred"], "sign in")

    def test_preferred_term_alone_passes(self) -> None:
        active = rule("required_terminology")
        self.assertEqual(required_terminology.evaluate(active, artifact({"title": "Sign in now"}))["status"], "PASS")

    def test_neither_term_passes_without_inventing_a_concept_requirement(self) -> None:
        active = rule("required_terminology")
        self.assertEqual(required_terminology.evaluate(active, artifact({"title": "Continue"}))["status"], "PASS")

    def test_rule_remains_field_scoped(self) -> None:
        active = rule("required_terminology")
        result = required_terminology.evaluate(active, artifact({"title": "Continue", "body": "Log in"}))
        self.assertEqual(result["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
