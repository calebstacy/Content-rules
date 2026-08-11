from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import unittest

from tests.helpers import ROOT
from content_rules import common
from content_rules.common import load_json
from content_rules.contextual import (
    MAX_CONDITIONS_PER_RULE,
    MAX_CONFLICT_GROUPS,
    MAX_GROUP_MEMBERS,
    MAX_INSTANCE_FACTS,
)


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

    def test_contextual_example_sources_and_receipts_are_fresh(self) -> None:
        example = ROOT / "examples" / "contextual-title-limits"
        source_bytes = (example / "guidance.md").read_bytes()
        rules = json.loads((example / "rules.json").read_text(encoding="utf-8"))
        candidates = json.loads((example / "candidates.json").read_text(encoding="utf-8"))
        digest = hashlib.sha256(source_bytes).hexdigest()
        self.assertEqual(rules["sources"][0]["sha256"], digest)
        self.assertEqual(candidates["source"]["sha256"], digest)
        lines = (example / "guidance.md").read_text(encoding="utf-8").splitlines()
        references = [
            ref
            for rule in rules["rules"]
            for ref in (
                rule["source_refs"]
                + rule.get("applies_when", {}).get("source_refs", [])
            )
        ] + [
            ref
            for group in rules["conflict_groups"]
            for edge in group["supersession"]
            for ref in edge["source_refs"]
        ]
        for ref in references:
            source_slice = "\n".join(lines[ref["line_start"] - 1 : ref["line_end"]])
            self.assertIn(ref["quote"], source_slice)

        cases = (
            ("artifact.pass.json", "receipt.pass.json", 0),
            ("artifact.fail.json", "receipt.fail.json", 1),
            ("artifact.review-missing.json", "receipt.review-missing.json", 3),
            ("artifact.review-conflict.json", "receipt.review-conflict.json", 3),
        )
        for artifact_name, receipt_name, expected_exit in cases:
            with self.subTest(artifact=artifact_name):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "run_checks.py"),
                        "check",
                        "--source-root",
                        str(example),
                        "--rules",
                        str(example / "rules.json"),
                        "--input",
                        str(example / artifact_name),
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, expected_exit)
                self.assertEqual(completed.stdout, (example / receipt_name).read_bytes())

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
        self.assertIn("Self-lint governed content", skill)
        self.assertIn("Run no more than five attempts", skill)
        self.assertIn("inferred", skill)
        self.assertIn("Never revise a contextual fact", skill)
        self.assertIn("numeric priority", skill)
        self.assertNotIn("python scripts/run_checks.py", skill)

    def test_any_agent_self_lint_loop_cannot_manufacture_a_pass(self) -> None:
        loop = (ROOT / "agents" / "self-lint.md").read_text(encoding="utf-8")
        self.assertIn("Before returning final content", loop)
        self.assertIn("On exit `1`", loop)
        self.assertIn("On exit `0`", loop)
        self.assertIn("On exit `3`", loop)
        self.assertIn("On exit `2`", loop)
        self.assertIn("Run at most five attempts", loop)
        self.assertIn("Do not change the rule set", loop)
        self.assertIn("must not change these assertions", loop)
        self.assertIn("must require a current receipt", loop)
        self.assertNotIn("blacklist", loop.casefold())
        self.assertNotIn("50", loop)

    def test_readme_explains_prompt_routing_and_human_authority(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("The prompt starts the workflow. It is not the enforcement mechanism.", readme)
        self.assertIn("Who makes FAIL matter?", readme)
        self.assertIn("Neither can authorize the rule", readme)
        self.assertIn("Make any agent self-lint", readme)
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

        rules_v2 = json.loads((ROOT / "schemas" / "rules-v2.schema.json").read_text(encoding="utf-8"))
        artifact_v2 = json.loads((ROOT / "schemas" / "artifact-v2.schema.json").read_text(encoding="utf-8"))
        receipt_v2 = json.loads((ROOT / "schemas" / "receipt-v2.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(rules_v2["properties"]["fact_definitions"]["maxItems"], common.MAX_FACT_DEFINITIONS)
        self.assertEqual(rules_v2["$defs"]["applies_when"]["properties"]["all"]["maxItems"], MAX_CONDITIONS_PER_RULE)
        self.assertEqual(rules_v2["properties"]["conflict_groups"]["maxItems"], MAX_CONFLICT_GROUPS)
        self.assertEqual(rules_v2["$defs"]["conflict_group"]["properties"]["members"]["maxItems"], MAX_GROUP_MEMBERS)
        self.assertEqual(artifact_v2["properties"]["facts"]["maxItems"], common.MAX_FACT_ASSERTIONS)
        self.assertEqual(artifact_v2["$defs"]["instance"]["properties"]["facts"]["maxItems"], MAX_INSTANCE_FACTS)
        self.assertEqual(
            receipt_v2["$defs"]["result"]["properties"]["evidence"]["maxItems"],
            common.MAX_RECEIPT_EVIDENCE_ITEMS_PER_RESULT,
        )
        self.assertEqual(
            receipt_v2["$defs"]["result"]["properties"]["review_evidence"]["maxItems"],
            common.MAX_RECEIPT_EVIDENCE_ITEMS_PER_RESULT,
        )

    def test_v2_public_contract_never_claims_authenticated_authority(self) -> None:
        candidates_schema = (ROOT / "schemas" / "candidates-v2.schema.json").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        migration = (ROOT / "MIGRATION.md").read_text(encoding="utf-8")
        formats = (ROOT / "references" / "formats.md").read_text(encoding="utf-8")
        self.assertNotIn('"authorized"', candidates_schema)
        self.assertIn("recorded_adopted", candidates_schema)
        self.assertIn("not authenticated authority", readme)
        self.assertIn("not authenticated", migration)
        self.assertIn("CLI remains the acceptance check", formats)


if __name__ == "__main__":
    unittest.main()
