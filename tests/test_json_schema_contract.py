from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from tests.helpers import ROOT

try:
    from jsonschema import Draft202012Validator, ValidationError
except ImportError:  # pragma: no cover - CI installs the pinned test dependency.
    Draft202012Validator = None  # type: ignore[assignment]
    ValidationError = Exception  # type: ignore[assignment]


def load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


@unittest.skipIf(Draft202012Validator is None, "install requirements-test.txt for JSON Schema gates")
class JsonSchemaContractTests(unittest.TestCase):
    def validator(self, schema_name: str) -> Draft202012Validator:
        schema = load(ROOT / "schemas" / schema_name)
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)

    def test_every_published_schema_is_a_valid_draft_2020_12_schema(self) -> None:
        for path in sorted((ROOT / "schemas").glob("*.schema.json")):
            with self.subTest(schema=path.name):
                Draft202012Validator.check_schema(load(path))

    def test_contextual_example_documents_validate_against_v2_schemas(self) -> None:
        example = ROOT / "examples" / "contextual-title-limits"
        cases = {
            "rules-v2.schema.json": [example / "rules.json"],
            "artifact-v2.schema.json": sorted(example.glob("artifact.*.json")),
            "candidates-v2.schema.json": [example / "candidates.json"],
            "receipt-v2.schema.json": sorted(example.glob("receipt.*.json")),
        }
        for schema_name, paths in cases.items():
            validator = self.validator(schema_name)
            for path in paths:
                with self.subTest(schema=schema_name, document=path.name):
                    validator.validate(load(path))

    def test_receipt_schema_rejects_raw_provenance_refs_and_missing_edge_table(self) -> None:
        example = ROOT / "examples" / "contextual-title-limits"
        receipt = load(example / "receipt.pass.json")
        self.assertIsInstance(receipt, dict)
        validator = self.validator("receipt-v2.schema.json")

        raw_ref = deepcopy(receipt)
        assertion = raw_ref["results"][1]["applicability"]["instances"][0]["facts"][0]["assertions"][0]
        assertion["ref"] = "C:/private/customer/source.json"
        with self.assertRaises(ValidationError):
            validator.validate(raw_ref)

        missing_edges = deepcopy(receipt)
        del missing_edges["precedence_evidence"]
        with self.assertRaises(ValidationError):
            validator.validate(missing_edges)

    def test_candidate_fact_values_must_match_their_declared_type(self) -> None:
        example = ROOT / "examples" / "contextual-title-limits"
        candidates = load(example / "candidates.json")
        self.assertIsInstance(candidates, dict)
        required_fact = candidates["units"][1]["required_facts"][0]
        required_fact["type"] = "boolean"
        required_fact["allowed_values"] = ["not-a-boolean"]

        with self.assertRaises(ValidationError):
            self.validator("candidates-v2.schema.json").validate(candidates)

    def test_contextual_schemas_reject_whitespace_only_semantic_values(self) -> None:
        example = ROOT / "examples" / "contextual-title-limits"

        rules = load(example / "rules.json")
        self.assertIsInstance(rules, dict)
        rule_mutations = {
            "rule-set name": lambda value: value["rule_set"].__setitem__("name", " \t "),
            "source path": lambda value: value["sources"][0].__setitem__("path", " \t "),
            "source quote": lambda value: value["rules"][0]["source_refs"][0].__setitem__("quote", " \t "),
            "fact scalar": lambda value: value["fact_definitions"][0].__setitem__("allowed_values", [" \t "]),
        }
        rules_validator = self.validator("rules-v2.schema.json")
        for label, mutate in rule_mutations.items():
            with self.subTest(schema="rules", value=label):
                invalid = deepcopy(rules)
                mutate(invalid)
                with self.assertRaises(ValidationError):
                    rules_validator.validate(invalid)

        artifact = load(example / "artifact.pass.json")
        self.assertIsInstance(artifact, dict)
        artifact_mutations = {
            "fact scalar": lambda value: value["instances"][0]["facts"][0].__setitem__("value", " \t "),
            "provenance ref": lambda value: value["instances"][0]["facts"][0]["provenance"].__setitem__("ref", " \t "),
            "surface": lambda value: value["instances"][0].__setitem__("surface", " \t "),
            "field name": lambda value: value["instances"][0].__setitem__("fields", {" \t ": "Title"}),
        }
        artifact_validator = self.validator("artifact-v2.schema.json")
        for label, mutate in artifact_mutations.items():
            with self.subTest(schema="artifact", value=label):
                invalid = deepcopy(artifact)
                mutate(invalid)
                with self.assertRaises(ValidationError):
                    artifact_validator.validate(invalid)

        candidates = load(example / "candidates.json")
        self.assertIsInstance(candidates, dict)
        candidate_mutations = {
            "fact scalar": lambda value: value["units"][1]["required_facts"][0].__setitem__("allowed_values", [" \t "]),
            "reason": lambda value: value["units"][1].__setitem__("reason", " \t "),
            "quote": lambda value: value["units"][1].__setitem__("quote", " \t "),
        }
        candidates_validator = self.validator("candidates-v2.schema.json")
        for label, mutate in candidate_mutations.items():
            with self.subTest(schema="candidates", value=label):
                invalid = deepcopy(candidates)
                mutate(invalid)
                with self.assertRaises(ValidationError):
                    candidates_validator.validate(invalid)


if __name__ == "__main__":
    unittest.main()
