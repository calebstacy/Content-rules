from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from . import TOOL_NAME, TOOL_VERSION
from . import banned_terms, character_limit, required_fields, required_terminology
from .common import RECEIPT_PROTOCOL, RULE_SET_PROTOCOL_V2, canonical_hash


Evaluator = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
EVALUATORS: dict[str, Evaluator] = {
    "banned_terms": banned_terms.evaluate,
    "character_limit": character_limit.evaluate,
    "required_terminology": required_terminology.evaluate,
    "required_fields": required_fields.evaluate,
}


def _run_checks_v1(
    rule_set: dict[str, Any],
    artifact: dict[str, Any],
    *,
    rules_path: Path,
    artifact_path: Path,
    rules_sha256: str,
    artifact_sha256: str,
    verified_sources: list[dict[str, str]],
) -> dict[str, Any]:
    results = [EVALUATORS[rule["check"]](rule, artifact) for rule in rule_set["rules"]]
    counts = {status: sum(result["status"] == status for result in results) for status in ("PASS", "FAIL", "REVIEW", "NOT_APPLICABLE")}
    if counts["FAIL"]:
        aggregate = "FAIL"
    elif counts["REVIEW"]:
        aggregate = "REVIEW"
    elif counts["PASS"]:
        aggregate = "PASS"
    else:
        aggregate = "NOT_APPLICABLE"
    applicable = counts["PASS"] + counts["FAIL"] + counts["REVIEW"]
    unresolved_evidence = sum(len(result["review_evidence"]) for result in results)
    metadata = rule_set["rule_set"]
    return {
        "protocol": RECEIPT_PROTOCOL,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "rule_set": {
            "id": metadata["id"],
            "name": metadata["name"],
            "status": metadata["status"],
            "owner": metadata["owner"],
            "decision_ref": metadata["decision_ref"],
            "effect": "check result only; the calling workflow decides consequences",
            "path": rules_path.name,
            "sha256": rules_sha256,
            "canonical_sha256": canonical_hash(rule_set),
        },
        "sources": verified_sources,
        "artifact": {
            "path": artifact_path.name,
            "sha256": artifact_sha256,
            "canonical_sha256": canonical_hash(artifact),
            "instance_count": len(artifact["instances"]),
        },
        "summary": {
            "status": aggregate,
            "applicable": applicable,
            "passed": counts["PASS"],
            "failed": counts["FAIL"],
            "review": counts["REVIEW"],
            "unresolved_evidence": unresolved_evidence,
            "not_applicable": counts["NOT_APPLICABLE"],
        },
        "results": results,
    }


def run_checks(
    rule_set: dict[str, Any],
    artifact: dict[str, Any],
    *,
    rules_path: Path,
    artifact_path: Path,
    rules_sha256: str,
    artifact_sha256: str,
    verified_sources: list[dict[str, str]],
) -> dict[str, Any]:
    from .contextual import validate_artifact_bindings

    validate_artifact_bindings(rule_set, artifact)
    if rule_set["schema_version"] == RULE_SET_PROTOCOL_V2:
        from .runtime_v2 import run_checks_v2

        return run_checks_v2(
            rule_set,
            artifact,
            evaluators=EVALUATORS,
            rules_path=rules_path,
            artifact_path=artifact_path,
            rules_sha256=rules_sha256,
            artifact_sha256=artifact_sha256,
            verified_sources=verified_sources,
        )
    return _run_checks_v1(
        rule_set,
        artifact,
        rules_path=rules_path,
        artifact_path=artifact_path,
        rules_sha256=rules_sha256,
        artifact_sha256=artifact_sha256,
        verified_sources=verified_sources,
    )


def exit_code(receipt: dict[str, Any]) -> int:
    status = receipt["summary"]["status"]
    if status == "PASS":
        return 0
    if status == "FAIL":
        return 1
    return 3
