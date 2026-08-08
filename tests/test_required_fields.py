from __future__ import annotations

import unittest

from tests.helpers import artifact, rule
from content_rules import required_fields


class RequiredFieldsTests(unittest.TestCase):
    def test_present_text_field_passes(self) -> None:
        active = rule("required_fields")
        self.assertEqual(required_fields.evaluate(active, artifact({"title": "Ready"}))["status"], "PASS")

    def test_absent_or_empty_required_field_fails(self) -> None:
        active = rule("required_fields")
        self.assertEqual(required_fields.evaluate(active, artifact({"body": "Ready"}))["status"], "FAIL")
        self.assertEqual(required_fields.evaluate(active, artifact({"title": "  "}))["status"], "FAIL")

    def test_empty_string_can_count_as_present_when_configured(self) -> None:
        active = rule("required_fields")
        active["params"]["require_non_empty"] = False
        self.assertEqual(required_fields.evaluate(active, artifact({"title": ""}))["status"], "PASS")

    def test_non_string_field_returns_review(self) -> None:
        active = rule("required_fields")
        active["params"]["require_non_empty"] = False
        self.assertEqual(required_fields.evaluate(active, artifact({"title": 42}))["status"], "REVIEW")

    def test_unmatched_surface_is_not_applicable(self) -> None:
        active = rule("required_fields")
        self.assertEqual(required_fields.evaluate(active, artifact({"title": "Ready"}, surface="toast"))["status"], "NOT_APPLICABLE")


if __name__ == "__main__":
    unittest.main()
