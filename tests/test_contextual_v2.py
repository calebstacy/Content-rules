from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any

from tests.helpers import ROOT, artifact, rule, rule_set, source, source_ref, write_json, write_source
from content_rules import common
from content_rules.common import RuleError, validate_artifact, validate_rule_set
from content_rules.runtime import run_checks


RUNNER = ROOT / "scripts" / "run_checks.py"


def fact_definition(
    fact_id: str,
    *,
    level: str = "instance",
    value_type: str = "string",
    allowed_values: list[Any] | None = None,
    accepted_sources: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    definition: dict[str, Any] = {
        "id": fact_id,
        "description": f"Context fixture for {fact_id}.",
        "level": level,
        "type": value_type,
        "accepted_sources": deepcopy(
            accepted_sources
            or [{"basis": "observed", "provider": "product-runtime"}]
        ),
    }
    if allowed_values is not None:
        definition["allowed_values"] = deepcopy(allowed_values)
    return definition


def fact_assertion(
    assertion_id: str,
    fact_id: str,
    value: Any,
    *,
    basis: str = "observed",
    provider: str = "product-runtime",
) -> dict[str, Any]:
    return {
        "id": assertion_id,
        "fact": fact_id,
        "value": deepcopy(value),
        "provenance": {
            "basis": basis,
            "provider": provider,
            "ref": f"fixture:{assertion_id}",
        },
    }


def applies_when(*leaves: dict[str, Any]) -> dict[str, Any]:
    return {
        "all": [deepcopy(leaf) for leaf in leaves],
        "source_refs": [source_ref()],
    }


def contextual_rule(
    check: str = "character_limit",
    *,
    rule_id: str,
    maximum: int = 5,
    condition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    configured = rule(check, rule_id=rule_id)
    if check == "character_limit":
        configured["params"]["maximum"] = maximum
    if condition is not None:
        configured["applies_when"] = deepcopy(condition)
    return configured


def conflict_group(
    group_id: str,
    members: list[str],
    *,
    supersession: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": group_id,
        "description": f"Competing fixture rules for {group_id}.",
        "members": list(members),
        "supersession": deepcopy(supersession or []),
    }


def supersession_edge(
    winner: str,
    loser: str,
    *,
    decision_ref: str | None,
) -> dict[str, Any]:
    return {
        "rule_id": winner,
        "supersedes": loser,
        "decision_ref": decision_ref,
        "source_refs": [source_ref()],
    }


def contextual_rule_set(
    *rules: dict[str, Any],
    facts: list[dict[str, Any]] | None = None,
    groups: list[dict[str, Any]] | None = None,
    adopted: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": "content-rule-set/2",
        "rule_set": {
            "id": "contextual-test-rules",
            "name": "Contextual test rules",
            "status": "adopted" if adopted else "proposed",
            "owner": "Content standards owner" if adopted else None,
            "decision_ref": "DECISION-RULE-SET" if adopted else None,
        },
        "sources": [source()] if rules or groups else [],
        "fact_definitions": deepcopy(facts or []),
        "rules": [deepcopy(item) for item in rules],
        "conflict_groups": deepcopy(groups or []),
    }


def content_instance(
    instance_id: str,
    fields: dict[str, Any],
    *,
    surface: str = "notice",
    facts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": instance_id,
        "surface": surface,
        "fields": deepcopy(fields),
        "facts": deepcopy(facts or []),
    }


def contextual_artifact(
    *instances: dict[str, Any],
    facts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "content-artifact/2",
        "facts": deepcopy(facts or []),
        "instances": [deepcopy(item) for item in instances],
    }


def direct_receipt(rules: dict[str, Any], content: dict[str, Any]) -> dict[str, Any]:
    validated_rules = validate_rule_set(deepcopy(rules))
    validated_artifact = validate_artifact(deepcopy(content))
    verified = [{**source(), "status": "VERIFIED"}] if rules["sources"] else []
    return run_checks(
        validated_rules,
        validated_artifact,
        rules_path=Path("rules.json"),
        artifact_path=Path("artifact.json"),
        rules_sha256="a" * 64,
        artifact_sha256="b" * 64,
        verified_sources=verified,
    )


def result_for(receipt: dict[str, Any], rule_id: str) -> dict[str, Any]:
    return next(result for result in receipt["results"] if result["rule_id"] == rule_id)


def assert_mentions(test: unittest.TestCase, value: Any, *needles: str) -> None:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True).casefold()
    for needle in needles:
        test.assertIn(needle.casefold(), serialized)


class ContextualApplicabilityTests(unittest.TestCase):
    def test_whitespace_only_context_values_are_rejected_by_runtime(self) -> None:
        definition = fact_definition("notice.variant", allowed_values=["standard"])
        rules = contextual_rule_set(facts=[definition])
        rules["rule_set"]["name"] = " \t "
        with self.assertRaises(RuleError):
            validate_rule_set(rules)

        artifact = contextual_artifact(
            content_instance(
                "notice-one",
                {"title": "Title"},
                facts=[fact_assertion("variant-one", "notice.variant", "standard")],
            )
        )
        artifact["instances"][0]["facts"][0]["provenance"]["ref"] = " \t "
        with self.assertRaises(RuleError):
            validate_artifact(artifact)

    def setUp(self) -> None:
        self.severity = fact_definition(
            "message.severity",
            allowed_values=["low", "high"],
        )
        self.high_only = applies_when(
            {"fact": "message.severity", "op": "equals", "value": "high"}
        )

    def test_true_false_and_missing_are_resolved_per_instance(self) -> None:
        configured = contextual_rule(
            rule_id="high-title-limit",
            maximum=5,
            condition=self.high_only,
        )
        rules = contextual_rule_set(configured, facts=[self.severity])
        content = contextual_artifact(
            content_instance(
                "high-notice",
                {"title": "123456"},
                facts=[fact_assertion("high-severity", "message.severity", "high")],
            ),
            content_instance(
                "low-notice",
                {"title": "this is deliberately long"},
                facts=[fact_assertion("low-severity", "message.severity", "low")],
            ),
            content_instance("unknown-notice", {"title": "also deliberately long"}),
        )

        receipt = direct_receipt(rules, content)
        result = result_for(receipt, "high-title-limit")

        self.assertEqual(receipt["protocol"], "content-rule-receipt/2")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(
            {item["instance_id"] for item in result["evidence"]},
            {"high-notice"},
        )
        self.assertGreaterEqual(len(result["review_evidence"]), 1)
        assert_mentions(self, result["review_evidence"], "unknown-notice", "message.severity")
        self.assertNotIn("low-notice", json.dumps(result["evidence"]))
        self.assertGreaterEqual(receipt["summary"]["unresolved_evidence"], 1)

    def test_definitively_false_condition_is_not_applicable(self) -> None:
        configured = contextual_rule(
            rule_id="high-title-limit",
            condition=self.high_only,
        )
        rules = contextual_rule_set(configured, facts=[self.severity])
        content = contextual_artifact(
            content_instance(
                "low-notice",
                {"title": "this would fail if the checker ran"},
                facts=[fact_assertion("low-severity", "message.severity", "low")],
            )
        )

        result = result_for(direct_receipt(rules, content), "high-title-limit")
        self.assertEqual(result["status"], "NOT_APPLICABLE")
        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["review_evidence"], [])

    def test_missing_fact_is_review_not_false_or_pass(self) -> None:
        configured = contextual_rule(
            rule_id="high-title-limit",
            condition=self.high_only,
        )
        rules = contextual_rule_set(configured, facts=[self.severity])
        content = contextual_artifact(
            content_instance("unknown-notice", {"title": "short"})
        )

        result = result_for(direct_receipt(rules, content), "high-title-limit")
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["evidence"], [])
        assert_mentions(self, result["review_evidence"], "unknown-notice", "message.severity")

    def test_inferred_or_unaccepted_provider_cannot_select_a_rule(self) -> None:
        configured = contextual_rule(
            rule_id="high-title-limit",
            condition=self.high_only,
        )
        rules = contextual_rule_set(configured, facts=[self.severity])
        unusable = (
            fact_assertion(
                "model-guess",
                "message.severity",
                "high",
                basis="inferred",
            ),
            fact_assertion(
                "unknown-provider",
                "message.severity",
                "high",
                provider="untrusted-adapter",
            ),
        )

        for assertion in unusable:
            with self.subTest(assertion=assertion["id"]):
                content = contextual_artifact(
                    content_instance(
                        "notice-01",
                        {"title": "this would fail if selected"},
                        facts=[assertion],
                    )
                )
                result = result_for(direct_receipt(rules, content), "high-title-limit")
                self.assertEqual(result["status"], "REVIEW")
                self.assertEqual(result["evidence"], [])
                assert_mentions(
                    self,
                    result["review_evidence"],
                    "message.severity",
                    assertion["id"],
                )

    def test_conflicting_accepted_values_are_review(self) -> None:
        configured = contextual_rule(
            rule_id="high-title-limit",
            condition=self.high_only,
        )
        rules = contextual_rule_set(configured, facts=[self.severity])
        content = contextual_artifact(
            content_instance(
                "notice-01",
                {"title": "this would fail if selected"},
                facts=[
                    fact_assertion("observed-high", "message.severity", "high"),
                    fact_assertion("observed-low", "message.severity", "low"),
                ],
            )
        )

        result = result_for(direct_receipt(rules, content), "high-title-limit")
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["evidence"], [])
        assert_mentions(
            self,
            result["review_evidence"],
            "message.severity",
            "observed-high",
            "observed-low",
        )

    def test_not_equals_and_one_of_are_supported_without_nested_logic(self) -> None:
        role = fact_definition("user.role", allowed_values=["admin", "guest"])
        region = fact_definition("user.region", allowed_values=["us", "uk", "eu"])
        condition = applies_when(
            {"fact": "user.role", "op": "not_equals", "value": "guest"},
            {"fact": "user.region", "op": "one_of", "values": ["uk", "eu"]},
        )
        configured = contextual_rule(
            rule_id="regional-admin-limit",
            maximum=10,
            condition=condition,
        )
        rules = contextual_rule_set(configured, facts=[role, region])
        content = contextual_artifact(
            content_instance(
                "notice-01",
                {"title": "short"},
                facts=[
                    fact_assertion("admin-role", "user.role", "admin"),
                    fact_assertion("uk-region", "user.region", "uk"),
                ],
            )
        )

        result = result_for(direct_receipt(rules, content), "regional-admin-limit")
        self.assertEqual(result["status"], "PASS")

    def test_false_condition_dominates_an_unknown_condition(self) -> None:
        audience = fact_definition(
            "message.audience",
            allowed_values=["consumer", "admin"],
        )
        configured = contextual_rule(
            rule_id="consumer-low-limit",
            condition=applies_when(
                {"fact": "message.severity", "op": "equals", "value": "low"},
                {"fact": "message.audience", "op": "equals", "value": "consumer"},
            ),
        )
        rules = contextual_rule_set(configured, facts=[self.severity, audience])
        content = contextual_artifact(
            content_instance(
                "notice-01",
                {"title": "this would fail if selected"},
                facts=[fact_assertion("high-severity", "message.severity", "high")],
            )
        )

        result = result_for(direct_receipt(rules, content), "consumer-low-limit")
        self.assertEqual(result["status"], "NOT_APPLICABLE")
        self.assertEqual(result["applicability"]["instances"][0]["condition"], "FALSE")

    def test_receipt_hashes_provenance_refs_and_disclaims_provider_authentication(self) -> None:
        configured = contextual_rule(
            rule_id="high-title-limit",
            condition=self.high_only,
        )
        rules = contextual_rule_set(configured, facts=[self.severity])
        assertion = fact_assertion("high-severity", "message.severity", "high")
        secret_reference = "C:/private/customer/account-42/source.json"
        assertion["provenance"]["ref"] = secret_reference
        content = contextual_artifact(
            content_instance(
                "notice-01",
                {"title": "short"},
                facts=[assertion],
            )
        )

        receipt = direct_receipt(rules, content)
        serialized = json.dumps(receipt, ensure_ascii=False)
        self.assertNotIn(secret_reference, serialized)
        trace = result_for(receipt, "high-title-limit")["applicability"]["instances"][0]["facts"][0]
        self.assertIn("ref_sha256", trace["assertions"][0])
        self.assertNotIn("ref", trace["assertions"][0])
        assert_mentions(self, receipt["rule_set"]["authority_note"], "provider", "trusted", "adapter")

    def test_artifact_level_fact_applies_to_each_matching_instance(self) -> None:
        release = fact_definition(
            "release.channel",
            level="artifact",
            allowed_values=["stable", "beta"],
        )
        condition = applies_when(
            {"fact": "release.channel", "op": "equals", "value": "beta"}
        )
        configured = contextual_rule(
            rule_id="beta-title-limit",
            maximum=3,
            condition=condition,
        )
        rules = contextual_rule_set(configured, facts=[release])
        content = contextual_artifact(
            content_instance("first-notice", {"title": "four"}),
            content_instance("second-notice", {"title": "five!"}),
            facts=[fact_assertion("beta-channel", "release.channel", "beta")],
        )

        result = result_for(direct_receipt(rules, content), "beta-title-limit")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(
            {item["instance_id"] for item in result["evidence"]},
            {"first-notice", "second-notice"},
        )

    def test_wrong_type_or_disallowed_value_is_an_invalid_artifact(self) -> None:
        configured = contextual_rule(
            rule_id="high-title-limit",
            condition=self.high_only,
        )
        rules = contextual_rule_set(configured, facts=[self.severity])
        invalid_assertions = (
            fact_assertion("wrong-type", "message.severity", 1),
            fact_assertion("outside-vocabulary", "message.severity", "critical"),
        )

        for assertion in invalid_assertions:
            with self.subTest(assertion=assertion["id"]):
                content = contextual_artifact(
                    content_instance(
                        "notice-01",
                        {"title": "short"},
                        facts=[assertion],
                    )
                )
                with self.assertRaises(RuleError):
                    direct_receipt(rules, content)


class ConflictResolutionTests(unittest.TestCase):
    def _pair(
        self,
        *,
        adopted: bool,
        edge_decision: str | None | object = ...,
        contextual: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        general = contextual_rule(rule_id="general-limit", maximum=5)
        facts: list[dict[str, Any]] = []
        condition = None
        if contextual:
            facts = [
                fact_definition(
                    "message.severity",
                    allowed_values=["low", "high"],
                )
            ]
            condition = applies_when(
                {"fact": "message.severity", "op": "equals", "value": "high"}
            )
        specific = contextual_rule(
            rule_id="specific-limit",
            maximum=10,
            condition=condition,
        )
        edges: list[dict[str, Any]] = []
        if edge_decision is not ...:
            edges.append(
                supersession_edge(
                    "specific-limit",
                    "general-limit",
                    decision_ref=edge_decision,
                )
            )
        group = conflict_group(
            "title-length",
            ["general-limit", "specific-limit"],
            supersession=edges,
        )
        rules = contextual_rule_set(
            general,
            specific,
            facts=facts,
            groups=[group],
            adopted=adopted,
        )
        return rules, general, specific

    def test_multiple_true_rules_without_winner_review_and_run_neither(self) -> None:
        rules, _, _ = self._pair(adopted=True)
        content = contextual_artifact(
            content_instance("notice-01", {"title": "this violates both limits"})
        )

        receipt = direct_receipt(rules, content)
        for rule_id in ("general-limit", "specific-limit"):
            result = result_for(receipt, rule_id)
            self.assertEqual(result["status"], "REVIEW")
            self.assertEqual(result["evidence"], [])
            assert_mentions(self, result["review_evidence"], "notice-01", "title-length")

    def test_adopted_edge_with_edge_decision_selects_winner(self) -> None:
        rules, _, _ = self._pair(adopted=True, edge_decision="DECISION-SPECIFIC-LIMIT")
        content = contextual_artifact(
            content_instance("notice-01", {"title": "1234567"})
        )

        receipt = direct_receipt(rules, content)
        self.assertEqual(result_for(receipt, "specific-limit")["status"], "PASS")
        loser = result_for(receipt, "general-limit")
        self.assertEqual(loser["status"], "NOT_APPLICABLE")
        self.assertEqual(loser["evidence"], [])
        assert_mentions(self, loser, "specific-limit", "DECISION-SPECIFIC-LIMIT")
        self.assertEqual(receipt["summary"]["status"], "PASS")
        resolution = receipt["resolutions"][0]
        self.assertEqual(len(resolution["precedence_edge_ids"]), 1)
        self.assertEqual(
            resolution["precedence_edge_ids"],
            [receipt["precedence_evidence"][0]["id"]],
        )
        self.assertEqual(receipt["precedence_evidence"][0]["source_refs"], [source_ref()])

    def test_transitive_precedence_records_every_supporting_edge(self) -> None:
        general = contextual_rule(rule_id="general-limit", maximum=5)
        intermediate = contextual_rule(rule_id="intermediate-limit", maximum=8)
        specific = contextual_rule(rule_id="specific-limit", maximum=10)
        rules = contextual_rule_set(
            general,
            intermediate,
            specific,
            groups=[
                conflict_group(
                    "title-length",
                    ["general-limit", "intermediate-limit", "specific-limit"],
                    supersession=[
                        supersession_edge(
                            "specific-limit",
                            "intermediate-limit",
                            decision_ref="DECISION-SPECIFIC",
                        ),
                        supersession_edge(
                            "intermediate-limit",
                            "general-limit",
                            decision_ref="DECISION-INTERMEDIATE",
                        ),
                    ],
                )
            ],
            adopted=True,
        )
        content = contextual_artifact(
            content_instance("notice-01", {"title": "1234567"})
        )

        receipt = direct_receipt(rules, content)
        resolution = receipt["resolutions"][0]
        self.assertEqual(resolution["selected_rule_id"], "specific-limit")
        self.assertEqual(len(resolution["precedence_edge_ids"]), 2)
        self.assertEqual(
            set(resolution["precedence_edge_ids"]),
            {edge["id"] for edge in receipt["precedence_evidence"]},
        )
        self.assertEqual(
            set(resolution["decision_refs"]),
            {"DECISION-SPECIFIC", "DECISION-INTERMEDIATE"},
        )

    def test_proposed_edge_is_inactive(self) -> None:
        rules, _, _ = self._pair(adopted=False, edge_decision=None)
        content = contextual_artifact(
            content_instance("notice-01", {"title": "this violates both limits"})
        )

        receipt = direct_receipt(rules, content)
        for rule_id in ("general-limit", "specific-limit"):
            result = result_for(receipt, rule_id)
            self.assertEqual(result["status"], "REVIEW")
            self.assertEqual(result["evidence"], [])

    def test_unknown_potential_winner_blocks_general_rule(self) -> None:
        rules, _, _ = self._pair(
            adopted=True,
            edge_decision="DECISION-SPECIFIC-LIMIT",
            contextual=True,
        )
        content = contextual_artifact(
            content_instance("notice-01", {"title": "this would fail the general rule"})
        )

        receipt = direct_receipt(rules, content)
        general = result_for(receipt, "general-limit")
        specific = result_for(receipt, "specific-limit")
        self.assertEqual(general["status"], "REVIEW")
        self.assertEqual(specific["status"], "REVIEW")
        self.assertEqual(general["evidence"], [])
        self.assertEqual(specific["evidence"], [])
        assert_mentions(self, receipt, "message.severity", "notice-01")

    def test_supersession_is_resolved_per_instance(self) -> None:
        rules, _, _ = self._pair(
            adopted=True,
            edge_decision="DECISION-SPECIFIC-LIMIT",
            contextual=True,
        )
        content = contextual_artifact(
            content_instance(
                "high-notice",
                {"title": "1234567"},
                facts=[fact_assertion("high-severity", "message.severity", "high")],
            ),
            content_instance(
                "low-notice",
                {"title": "1234567"},
                facts=[fact_assertion("low-severity", "message.severity", "low")],
            ),
        )

        receipt = direct_receipt(rules, content)
        general = result_for(receipt, "general-limit")
        specific = result_for(receipt, "specific-limit")
        self.assertEqual(general["status"], "FAIL")
        self.assertEqual(
            {item["instance_id"] for item in general["evidence"]},
            {"low-notice"},
        )
        self.assertEqual(specific["status"], "PASS")
        self.assertNotIn("high-notice", json.dumps(general["evidence"]))

    def test_rule_order_does_not_change_resolution(self) -> None:
        rules, general, specific = self._pair(
            adopted=True,
            edge_decision="DECISION-SPECIFIC-LIMIT",
        )
        reversed_rules = contextual_rule_set(
            specific,
            general,
            groups=[
                conflict_group(
                    "title-length",
                    ["specific-limit", "general-limit"],
                    supersession=[
                        supersession_edge(
                            "specific-limit",
                            "general-limit",
                            decision_ref="DECISION-SPECIFIC-LIMIT",
                        )
                    ],
                )
            ],
            adopted=True,
        )
        content = contextual_artifact(
            content_instance("notice-01", {"title": "1234567"})
        )

        first = direct_receipt(rules, content)
        second = direct_receipt(reversed_rules, content)
        self.assertEqual(first["summary"], second["summary"])
        self.assertEqual(
            {item["rule_id"]: item["status"] for item in first["results"]},
            {item["rule_id"]: item["status"] for item in second["results"]},
        )

    def test_invalid_supersession_graphs_and_priority_are_rejected(self) -> None:
        a = contextual_rule(rule_id="rule-a")
        b = contextual_rule(rule_id="rule-b")
        c = contextual_rule(rule_id="rule-c")
        fixtures: dict[str, dict[str, Any]] = {
            "self": contextual_rule_set(
                a,
                b,
                groups=[
                    conflict_group(
                        "group-a",
                        ["rule-a", "rule-b"],
                        supersession=[
                            supersession_edge("rule-a", "rule-a", decision_ref="DECISION-SELF")
                        ],
                    )
                ],
                adopted=True,
            ),
            "cycle": contextual_rule_set(
                a,
                b,
                groups=[
                    conflict_group(
                        "group-a",
                        ["rule-a", "rule-b"],
                        supersession=[
                            supersession_edge("rule-a", "rule-b", decision_ref="DECISION-A"),
                            supersession_edge("rule-b", "rule-a", decision_ref="DECISION-B"),
                        ],
                    )
                ],
                adopted=True,
            ),
            "unknown-member": contextual_rule_set(
                a,
                groups=[conflict_group("group-a", ["rule-a", "missing-rule"])],
                adopted=True,
            ),
            "cross-group": contextual_rule_set(
                a,
                b,
                c,
                groups=[
                    conflict_group(
                        "group-a",
                        ["rule-a", "rule-b"],
                        supersession=[
                            supersession_edge("rule-a", "rule-c", decision_ref="DECISION-CROSS")
                        ],
                    ),
                    conflict_group("group-b", ["rule-c"]),
                ],
                adopted=True,
            ),
        }
        priority = contextual_rule_set(a)
        priority["rules"][0]["priority"] = 100
        fixtures["priority"] = priority

        for name, configured in fixtures.items():
            with self.subTest(name=name):
                with self.assertRaises(RuleError):
                    validate_rule_set(configured)

    def test_canonically_equivalent_terminology_conflicts_are_rejected(self) -> None:
        composed = contextual_rule(
            "required_terminology",
            rule_id="composed-term",
        )
        composed["params"].update(
            {
                "preferred": "coffee",
                "instead_of": ["caf\u00e9"],
                "case_sensitive": True,
            }
        )
        decomposed = contextual_rule(
            "required_terminology",
            rule_id="decomposed-term",
        )
        decomposed["params"].update(
            {
                "preferred": "tea",
                "instead_of": ["cafe\u0301"],
                "case_sensitive": True,
            }
        )

        with self.assertRaisesRegex(RuleError, "explicit conflict group"):
            validate_rule_set(contextual_rule_set(composed, decomposed))

    def test_conditions_reference_defined_facts_and_remain_flat(self) -> None:
        unknown_fact = contextual_rule(
            rule_id="unknown-fact",
            condition=applies_when(
                {"fact": "not.defined", "op": "equals", "value": "yes"}
            ),
        )
        with self.assertRaises(RuleError):
            validate_rule_set(contextual_rule_set(unknown_fact))

        nested = contextual_rule(rule_id="nested-condition")
        nested["applies_when"] = {
            "any": [{"fact": "message.severity", "op": "equals", "value": "high"}],
            "source_refs": [source_ref()],
        }
        with self.assertRaises(RuleError):
            validate_rule_set(contextual_rule_set(nested, facts=[fact_definition("message.severity")]))

        repeated_fact = contextual_rule(
            rule_id="repeated-fact",
            condition=applies_when(
                {"fact": "message.severity", "op": "not_equals", "value": "low"},
                {"fact": "message.severity", "op": "not_equals", "value": "high"},
            ),
        )
        with self.assertRaisesRegex(RuleError, "only one condition"):
            validate_rule_set(
                contextual_rule_set(
                    repeated_fact,
                    facts=[fact_definition("message.severity")],
                )
            )


class ContextualCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, str(RUNNER), *args],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )

    def test_receipt_v2_is_deterministic_and_matches_written_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_source(root)
            rules_path = root / "rules.json"
            input_path = root / "input.json"
            receipt_path = root / "receipt.json"
            severity = fact_definition(
                "message.severity",
                allowed_values=["low", "high"],
            )
            configured = contextual_rule(
                rule_id="high-title-limit",
                maximum=10,
                condition=applies_when(
                    {"fact": "message.severity", "op": "equals", "value": "high"}
                ),
            )
            write_json(rules_path, contextual_rule_set(configured, facts=[severity]))
            write_json(
                input_path,
                contextual_artifact(
                    content_instance(
                        "notice-01",
                        {"title": "short"},
                        facts=[fact_assertion("high-severity", "message.severity", "high")],
                    )
                ),
            )

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
            second = self.run_cli(
                "check",
                "--source-root",
                str(root),
                "--rules",
                str(rules_path),
                "--input",
                str(input_path),
            )

            self.assertEqual(first.returncode, 0)
            self.assertEqual(first.stdout, second.stdout)
            self.assertEqual(first.stdout, receipt_path.read_bytes())
            self.assertEqual(json.loads(first.stdout)["protocol"], "content-rule-receipt/2")

    def test_mixed_protocols_are_structured_errors_in_both_directions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_source(root)
            v1_rules = root / "v1-rules.json"
            v2_rules = root / "v2-rules.json"
            v1_input = root / "v1-input.json"
            v2_input = root / "v2-input.json"
            write_json(v1_rules, rule_set(rule("character_limit")))
            write_json(
                v2_rules,
                contextual_rule_set(contextual_rule(rule_id="title-limit")),
            )
            write_json(v1_input, artifact({"title": "short"}))
            write_json(
                v2_input,
                contextual_artifact(content_instance("notice-01", {"title": "short"})),
            )

            pairs = ((v1_rules, v2_input), (v2_rules, v1_input))
            for rules_path, input_path in pairs:
                with self.subTest(rules=rules_path.name, artifact=input_path.name):
                    completed = self.run_cli(
                        "check",
                        "--source-root",
                        str(root),
                        "--rules",
                        str(rules_path),
                        "--input",
                        str(input_path),
                    )
                    payload = json.loads(completed.stdout)
                    self.assertEqual(completed.returncode, 2)
                    self.assertEqual(payload["error"]["code"], "INCOMPATIBLE_PROTOCOLS")

    def test_v1_still_emits_receipt_v1_with_existing_status_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_source(root)
            write_json(root / "rules.json", rule_set(rule("character_limit")))
            write_json(root / "input.json", artifact({"title": "short"}))
            completed = self.run_cli(
                "check",
                "--source-root",
                str(root),
                "--rules",
                str(root / "rules.json"),
                "--input",
                str(root / "input.json"),
            )
            payload = json.loads(completed.stdout)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(payload["protocol"], "content-rule-receipt/1")
            self.assertEqual(payload["summary"]["status"], "PASS")

    def test_fact_definition_and_assertion_limits_are_enforced(self) -> None:
        definition_limit = getattr(common, "MAX_FACT_DEFINITIONS")
        assertion_limit = getattr(common, "MAX_FACT_ASSERTIONS")
        self.assertGreater(definition_limit, 0)
        self.assertGreater(assertion_limit, 0)

        too_many_definitions = contextual_rule_set(
            facts=[
                fact_definition(f"fact-{index}")
                for index in range(definition_limit + 1)
            ]
        )
        with self.assertRaises(RuleError):
            validate_rule_set(too_many_definitions)

        too_many_assertions = contextual_artifact(
            content_instance("notice-01", {"title": "short"}),
            facts=[
                fact_assertion(f"assertion-{index}", "shared.fact", "same")
                for index in range(assertion_limit + 1)
            ],
        )
        with self.assertRaises(RuleError):
            validate_artifact(too_many_assertions)

    def test_rule_instance_evaluation_limit_stops_before_checking(self) -> None:
        evaluation_limit = getattr(common, "MAX_RULE_INSTANCE_EVALUATIONS")
        self.assertGreater(evaluation_limit, 0)
        self.assertLess(evaluation_limit, 200 * 1000)
        rule_count = min(200, evaluation_limit + 1)
        instance_count = evaluation_limit // rule_count + 1
        self.assertLessEqual(instance_count, 1000)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_source(root)
            configured_rules = [
                contextual_rule(rule_id=f"limit-{index}")
                for index in range(rule_count)
            ]
            instances = [
                content_instance(f"notice-{index}", {"title": "short"})
                for index in range(instance_count)
            ]
            write_json(root / "rules.json", contextual_rule_set(*configured_rules))
            write_json(root / "input.json", contextual_artifact(*instances))

            completed = self.run_cli(
                "check",
                "--source-root",
                str(root),
                "--rules",
                str(root / "rules.json"),
                "--input",
                str(root / "input.json"),
            )
            payload = json.loads(completed.stdout)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(payload["status"], "ERROR")
            assert_mentions(self, payload["error"], "evaluation")

    def test_receipt_detail_limit_stops_trace_amplification(self) -> None:
        severity = fact_definition(
            "message.severity",
            allowed_values=["high"],
        )
        configured_rules = [
            contextual_rule(
                rule_id=f"limit-{index}",
                condition=applies_when(
                    {"fact": "message.severity", "op": "equals", "value": "high"}
                ),
            )
            for index in range(101)
        ]
        instances = [
            content_instance(
                f"notice-{instance_index}",
                {"title": "short"},
                facts=[
                    fact_assertion(
                        f"severity-{instance_index}-{assertion_index}",
                        "message.severity",
                        "high",
                    )
                    for assertion_index in range(50)
                ],
            )
            for instance_index in range(5)
        ]
        rules = contextual_rule_set(*configured_rules, facts=[severity])
        content = contextual_artifact(*instances)

        with self.assertRaises(RuleError) as raised:
            direct_receipt(rules, content)
        self.assertEqual(raised.exception.code, "RECEIPT_DETAIL_LIMIT")

    def test_receipt_detail_limit_stops_schema_invalid_checker_evidence(self) -> None:
        configured = contextual_rule(
            rule_id="two-field-limit",
            maximum=0,
        )
        configured["scope"]["fields"] = ["title", "body"]
        rules = contextual_rule_set(configured)
        content = contextual_artifact(
            *[
                content_instance(
                    f"notice-{index}",
                    {"title": "x", "body": "x"},
                )
                for index in range(1000)
            ]
        )

        with self.assertRaises(RuleError) as raised:
            direct_receipt(rules, content)
        self.assertEqual(raised.exception.code, "RECEIPT_DETAIL_LIMIT")

    def test_receipt_detail_limit_counts_empty_star_scopes_as_review_evidence(self) -> None:
        configured = contextual_rule(
            rule_id="all-field-limit",
            maximum=10,
        )
        configured["scope"]["fields"] = ["*"]
        rules = contextual_rule_set(configured)
        empty_instances = [
            content_instance(f"empty-{index}", {})
            for index in range(999)
        ]
        non_text_fields = {f"field-{index}": None for index in range(200)}
        content = contextual_artifact(
            *empty_instances,
            content_instance("non-text", non_text_fields),
        )

        with self.assertRaises(RuleError) as raised:
            direct_receipt(rules, content)
        self.assertEqual(raised.exception.code, "RECEIPT_DETAIL_LIMIT")


if __name__ == "__main__":
    unittest.main()
