from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import unittest

from tests.helpers import ROOT
from content_rules.common import load_json


class RepositoryContractTests(unittest.TestCase):
    def test_every_checked_in_json_file_parses(self) -> None:
        for path in sorted(ROOT.rglob("*.json")):
            with self.subTest(path=path.relative_to(ROOT)):
                load_json(path, "INVALID_REPOSITORY_JSON")

    def test_example_source_hash_and_line_quotes_are_real(self) -> None:
        example = ROOT / "examples" / "workspace-deletion"
        source_bytes = (example / "guidance.md").read_bytes()
        rules = json.loads((example / "rules.json").read_text(encoding="utf-8"))
        candidates = json.loads((example / "candidates.json").read_text(encoding="utf-8"))
        digest = hashlib.sha256(source_bytes).hexdigest()
        self.assertEqual(rules["sources"][0]["sha256"], digest)
        self.assertEqual(candidates["source"]["sha256"], digest)
        lines = (example / "guidance.md").read_text(encoding="utf-8").splitlines()
        for rule in rules["rules"]:
            for ref in rule["source_refs"]:
                source_slice = "\n".join(lines[ref["line_start"] - 1 : ref["line_end"]])
                self.assertIn(ref["quote"], source_slice)

    def test_checked_in_failure_receipt_is_fresh(self) -> None:
        example = ROOT / "examples" / "workspace-deletion"
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "run_checks.py"),
                "check",
                "--rules",
                str(example / "rules.json"),
                "--input",
                str(example / "artifact.fail.json"),
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, (example / "receipt.fail.json").read_bytes())

    def test_skill_is_complete_and_keeps_the_runtime_fixed(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("TODO", skill)
        self.assertIn("Do not modify checker code", skill)
        for check in (
            "banned_terms",
            "character_limit",
            "required_terminology",
            "required_fields",
        ):
            self.assertIn(check, skill)
        self.assertNotIn("Word Math", skill)
        self.assertNotIn("Pajamas", skill)
        self.assertIn("KIT_ROOT", skill)
        self.assertIn("PROJECT_ROOT", skill)
        self.assertIn("counting unit", skill)
        self.assertIn("omit that rule from `rules.json`", skill)
        self.assertIn("proposal-local surface or field mapping", skill)
        self.assertIn("deliberately failing fixture should exit `1`", skill)
        self.assertNotIn("python scripts/run_checks.py", skill)

    def test_readme_explains_prompt_routing_and_human_authority(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("The prompt starts the workflow. It is not the enforcement mechanism.", readme)
        self.assertIn("Who makes FAIL matter?", readme)
        self.assertIn("Neither can authorize the rule", readme)
        self.assertIn("__REPLACE_ME__", readme)
        self.assertIn("whole-term-versus-substring behavior", readme)
        self.assertNotIn("check \\\n", readme)
        self.assertNotIn("Word Math", readme)

    def test_routing_prompt_points_to_the_check_without_copying_policy(self) -> None:
        prompt = (ROOT / "examples" / "workspace-deletion" / "routing.prompt.md").read_text(encoding="utf-8")
        self.assertIn("<KIT_ROOT>/scripts/run_checks.py", prompt)
        self.assertIn("--source-root \"<PROJECT_ROOT>\"", prompt)
        self.assertNotIn("50", prompt)
        self.assertNotIn("blacklist", prompt.casefold())
        self.assertNotIn("whitelist", prompt.casefold())

    def test_templates_use_reserved_sentinels_not_natural_language_markers(self) -> None:
        for path in sorted((ROOT / "templates").glob("*.json")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("__REPLACE_ME__", text)
                self.assertNotIn("replace-with", text.casefold())

    def test_published_schema_limits_match_runtime_boundaries(self) -> None:
        rules_schema = json.loads((ROOT / "schemas" / "rules.schema.json").read_text(encoding="utf-8"))
        artifact_schema = json.loads((ROOT / "schemas" / "artifact.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(rules_schema["properties"]["sources"]["maxItems"], 50)
        self.assertEqual(rules_schema["properties"]["rules"]["maxItems"], 200)
        self.assertEqual(rules_schema["$defs"]["rule"]["properties"]["source_refs"]["maxItems"], 20)
        self.assertEqual(artifact_schema["properties"]["instances"]["maxItems"], 1000)
        source_pattern = re.compile(rules_schema["$defs"]["source"]["properties"]["path"]["pattern"])
        self.assertIsNotNone(source_pattern.search("standards/guidance.md"))
        for unsafe in ("../guidance.md", "standards/../guidance.md", "C:/guidance.md", "https://example.com"):
            with self.subTest(unsafe=unsafe):
                self.assertIsNone(source_pattern.search(unsafe))


if __name__ == "__main__":
    unittest.main()
