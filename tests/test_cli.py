from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT, artifact, rule, rule_set, write_json, write_source


RUNNER = ROOT / "scripts" / "run_checks.py"


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, str(RUNNER), *args],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )

    def test_exit_codes_cover_pass_fail_error_review_and_not_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules_path = root / "rules.json"
            input_path = root / "input.json"
            write_source(root)
            active = rule("banned_terms")
            write_json(rules_path, rule_set(active))
            write_json(input_path, artifact({"title": "Clear"}))
            self.assertEqual(self.run_cli("check", "--source-root", str(root), "--rules", str(rules_path), "--input", str(input_path)).returncode, 0)
            write_json(input_path, artifact({"title": "log"}))
            self.assertEqual(self.run_cli("check", "--source-root", str(root), "--rules", str(rules_path), "--input", str(input_path)).returncode, 1)
            input_path.write_text("{", encoding="utf-8")
            self.assertEqual(self.run_cli("check", "--source-root", str(root), "--rules", str(rules_path), "--input", str(input_path)).returncode, 2)
            write_json(input_path, artifact({"body": "Clear"}))
            self.assertEqual(self.run_cli("check", "--source-root", str(root), "--rules", str(rules_path), "--input", str(input_path)).returncode, 3)
            write_json(rules_path, rule_set())
            self.assertEqual(self.run_cli("check", "--source-root", str(root), "--rules", str(rules_path), "--input", str(input_path)).returncode, 3)

    def test_failure_takes_precedence_over_missing_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_source(root)
            first = rule("banned_terms", rule_id="fails")
            first["scope"]["fields"] = ["body"]
            second = rule("character_limit", rule_id="reviews")
            write_json(root / "rules.json", rule_set(first, second))
            write_json(root / "input.json", artifact({"body": "log"}))
            completed = self.run_cli(
                "check",
                "--source-root",
                str(root),
                "--rules",
                str(root / "rules.json"),
                "--input",
                str(root / "input.json"),
            )
            receipt = json.loads(completed.stdout)
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(receipt["summary"]["status"], "FAIL")
            self.assertEqual(receipt["summary"]["failed"], 1)
            self.assertEqual(receipt["summary"]["review"], 1)

    def test_one_rule_keeps_missing_evidence_visible_beside_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_source(root)
            configured = rule("banned_terms")
            configured["scope"]["fields"] = ["title", "body"]
            write_json(root / "rules.json", rule_set(configured))
            write_json(root / "input.json", artifact({"body": "log"}))
            completed = self.run_cli(
                "check",
                "--source-root",
                str(root),
                "--rules",
                str(root / "rules.json"),
                "--input",
                str(root / "input.json"),
            )
            receipt = json.loads(completed.stdout)
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(receipt["results"][0]["status"], "FAIL")
            self.assertEqual(receipt["results"][0]["review_evidence"][0]["field"], "title")
            self.assertEqual(receipt["summary"]["review"], 0)
            self.assertEqual(receipt["summary"]["unresolved_evidence"], 1)

    def test_receipt_is_byte_identical_and_output_equals_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules_path = root / "rules.json"
            input_path = root / "input.json"
            receipt_path = root / "receipt.json"
            write_source(root)
            active = rule("banned_terms")
            active["description"] = "Keep café terminology out of this field."
            write_json(rules_path, rule_set(active))
            write_json(input_path, artifact({"title": "Clear café"}))
            first = self.run_cli(
                "check",
                "--source-root",
                str(root),
                "--rules",
                str(rules_path),
                "--input",
                str(input_path),
                "--receipt",
                str(receipt_path),
            )
            second = self.run_cli("check", "--source-root", str(root), "--rules", str(rules_path), "--input", str(input_path))
            self.assertEqual(first.returncode, 0)
            self.assertEqual(first.stdout, second.stdout)
            self.assertEqual(first.stdout, receipt_path.read_bytes())
            self.assertTrue(first.stdout.endswith(b"\n"))
            self.assertIn("café".encode("utf-8"), first.stdout)
            self.assertEqual(json.loads(first.stdout)["sources"][0]["status"], "VERIFIED")

    def test_receipt_hashes_the_exact_bounded_bytes_that_were_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules_path = root / "rules.json"
            input_path = root / "input.json"
            write_source(root)
            write_json(rules_path, rule_set(rule("banned_terms")))
            artifact_bytes = b"\xef\xbb\xbf" + json.dumps(artifact({"title": "Clear"}), sort_keys=True).encode("utf-8")
            input_path.write_bytes(artifact_bytes)
            completed = self.run_cli(
                "check",
                "--source-root",
                str(root),
                "--rules",
                str(rules_path),
                "--input",
                str(input_path),
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["artifact"]["sha256"], hashlib.sha256(artifact_bytes).hexdigest())

    def test_changed_source_stops_the_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules_path = root / "rules.json"
            input_path = root / "input.json"
            write_source(root)
            write_json(rules_path, rule_set(rule("banned_terms")))
            write_json(input_path, artifact({"title": "Clear"}))
            (root / "guidance.md").write_text("Changed source.\n", encoding="utf-8", newline="\n")
            completed = self.run_cli("check", "--source-root", str(root), "--rules", str(rules_path), "--input", str(input_path))
            payload = json.loads(completed.stdout)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(payload["error"]["code"], "SOURCE_HASH_MISMATCH")

    def test_false_source_quote_stops_the_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules_path = root / "rules.json"
            input_path = root / "input.json"
            write_source(root)
            configured = rule("banned_terms")
            configured["source_refs"][0]["quote"] = "Words that are not in the source."
            write_json(rules_path, rule_set(configured))
            write_json(input_path, artifact({"title": "Clear"}))
            completed = self.run_cli("check", "--source-root", str(root), "--rules", str(rules_path), "--input", str(input_path))
            payload = json.loads(completed.stdout)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(payload["error"]["code"], "SOURCE_REF_MISMATCH")

    def test_invalid_utf8_is_structured_and_has_no_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules_path = root / "rules.json"
            input_path = root / "input.json"
            write_source(root)
            write_json(rules_path, rule_set(rule("banned_terms")))
            input_path.write_bytes(b"\xff\xfe\x00")
            completed = self.run_cli("check", "--source-root", str(root), "--rules", str(rules_path), "--input", str(input_path))
            payload = json.loads(completed.stdout)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(payload["status"], "ERROR")
            self.assertNotIn(b"Traceback", completed.stdout + completed.stderr)

    def test_duplicate_keys_and_invalid_unicode_are_structured_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules_path = root / "rules.json"
            input_path = root / "input.json"
            write_source(root)
            write_json(rules_path, rule_set(rule("banned_terms")))

            input_path.write_text(
                '{"schema_version":"content-artifact/1","instances":[{"id":"first","id":"second","surface":"test","fields":{"title":"Clear"}}]}',
                encoding="utf-8",
            )
            duplicate = self.run_cli(
                "check",
                "--source-root",
                str(root),
                "--rules",
                str(rules_path),
                "--input",
                str(input_path),
            )
            self.assertEqual(duplicate.returncode, 2)
            self.assertEqual(json.loads(duplicate.stdout)["error"]["code"], "INVALID_ARTIFACT_JSON")
            self.assertNotIn(b"Traceback", duplicate.stdout + duplicate.stderr)

            input_path.write_text(
                r'{"schema_version":"content-artifact/1","instances":[{"id":"first","surface":"test","fields":{"title":"\ud800"}}]}',
                encoding="utf-8",
            )
            surrogate = self.run_cli(
                "check",
                "--source-root",
                str(root),
                "--rules",
                str(rules_path),
                "--input",
                str(input_path),
            )
            self.assertEqual(surrogate.returncode, 2)
            self.assertEqual(json.loads(surrogate.stdout)["error"]["code"], "INVALID_ARTIFACT_JSON")
            self.assertNotIn(b"Traceback", surrogate.stdout + surrogate.stderr)

    def test_non_finite_and_oversized_json_numbers_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules_path = root / "rules.json"
            input_path = root / "input.json"
            write_source(root)
            write_json(rules_path, rule_set(rule("banned_terms")))
            for value in ("NaN", "1e1000", "1" * 101):
                with self.subTest(value=value[:20]):
                    input_path.write_text(
                        '{"schema_version":"content-artifact/1","instances":[{"id":"first","surface":"test","fields":{"title":'
                        + value
                        + "}}]}",
                        encoding="utf-8",
                    )
                    completed = self.run_cli(
                        "check",
                        "--source-root",
                        str(root),
                        "--rules",
                        str(rules_path),
                        "--input",
                        str(input_path),
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertEqual(json.loads(completed.stdout)["error"]["code"], "INVALID_ARTIFACT_JSON")
                    self.assertNotIn(b"Traceback", completed.stdout + completed.stderr)

    def test_receipt_cannot_replace_input_and_existing_output_needs_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules_path = root / "rules.json"
            input_path = root / "input.json"
            receipt_path = root / "receipt.json"
            write_source(root)
            write_json(rules_path, rule_set(rule("banned_terms")))
            write_json(input_path, artifact({"title": "Clear"}))
            unsafe = self.run_cli(
                "check",
                "--source-root",
                str(root),
                "--rules",
                str(rules_path),
                "--input",
                str(input_path),
                "--receipt",
                str(input_path),
            )
            self.assertEqual(unsafe.returncode, 2)
            self.assertEqual(json.loads(input_path.read_text(encoding="utf-8"))["schema_version"], "content-artifact/1")
            receipt_path.write_text("keep", encoding="utf-8")
            blocked = self.run_cli(
                "check",
                "--source-root",
                str(root),
                "--rules",
                str(rules_path),
                "--input",
                str(input_path),
                "--receipt",
                str(receipt_path),
            )
            self.assertEqual(blocked.returncode, 2)
            self.assertEqual(receipt_path.read_text(encoding="utf-8"), "keep")
            replaced = self.run_cli(
                "check",
                "--source-root",
                str(root),
                "--rules",
                str(rules_path),
                "--input",
                str(input_path),
                "--receipt",
                str(receipt_path),
                "--force",
            )
            self.assertEqual(replaced.returncode, 0)

    def test_receipt_cannot_replace_a_verified_source_even_with_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules_path = root / "rules.json"
            input_path = root / "input.json"
            source_path = root / "guidance.md"
            write_source(root)
            source_before = source_path.read_bytes()
            write_json(rules_path, rule_set(rule("banned_terms")))
            write_json(input_path, artifact({"title": "Clear"}))
            completed = self.run_cli(
                "check",
                "--source-root",
                str(root),
                "--rules",
                str(rules_path),
                "--input",
                str(input_path),
                "--receipt",
                str(source_path),
                "--force",
            )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(json.loads(completed.stdout)["error"]["code"], "UNSAFE_OUTPUT")
            self.assertEqual(source_path.read_bytes(), source_before)

    def test_example_produces_four_expected_failures(self) -> None:
        example = ROOT / "examples" / "workspace-deletion"
        completed = self.run_cli(
            "check",
            "--rules",
            str(example / "rules.json"),
            "--input",
            str(example / "artifact.fail.json"),
        )
        receipt = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(receipt["summary"]["failed"], 4)
        self.assertEqual(receipt["results"][0]["evidence"][0]["measured"], 62)


if __name__ == "__main__":
    unittest.main()
