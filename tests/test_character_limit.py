from __future__ import annotations

import unittest

from tests.helpers import artifact, rule
from content_rules import character_limit


class CharacterLimitTests(unittest.TestCase):
    def test_exactly_at_limit_passes_and_one_over_fails(self) -> None:
        active = rule("character_limit")
        self.assertEqual(character_limit.evaluate(active, artifact({"title": "1234567890"}))["status"], "PASS")
        self.assertEqual(character_limit.evaluate(active, artifact({"title": "12345678901"}))["status"], "FAIL")

    def test_newline_counts_as_a_code_point(self) -> None:
        active = rule("character_limit")
        active["params"]["maximum"] = 2
        result = character_limit.evaluate(active, artifact({"title": "a\nb"}))
        self.assertEqual(result["evidence"][0]["measured"], 3)

    def test_nfc_composition_counts_e_acute_as_one(self) -> None:
        active = rule("character_limit")
        active["params"]["maximum"] = 1
        self.assertEqual(character_limit.evaluate(active, artifact({"title": "e\u0301"}))["status"], "PASS")

    def test_zwj_emoji_count_is_code_points_not_graphemes(self) -> None:
        active = rule("character_limit")
        active["params"]["maximum"] = 2
        result = character_limit.evaluate(active, artifact({"title": "👩‍💻"}))
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["evidence"][0]["measured"], 3)

    def test_missing_target_returns_review(self) -> None:
        active = rule("character_limit")
        self.assertEqual(character_limit.evaluate(active, artifact({"body": "short"}))["status"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
