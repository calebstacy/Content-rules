from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from . import TOOL_NAME, TOOL_VERSION
from .common import (
    MAX_RECEIPT_BYTES,
    MAX_RECEIPT_EVIDENCE_ITEMS_PER_RESULT,
    MAX_RECEIPT_TRACE_UNITS,
    RECEIPT_PROTOCOL_V2,
    RuleError,
    canonical_hash,
    canonical_json,
    matching_instances,
    result_base,
)
from .contextual import MAX_RULE_INSTANCE_EVALUATIONS, evaluate_applicability


def _condition_state(outcome: str) -> str:
    if outcome == "TRUE":
        return "CONDITION_TRUE"
    if outcome == "FALSE":
        return "CONDITION_FALSE"
    if outcome == "CONFLICT":
        return "FACT_CONFLICT"
    return "UNKNOWN_FACT"


def _applicability_record(
    *,
    instance_id: str,
    outcome: str,
    facts: list[dict[str, Any]],
    group_id: str | None,
) -> dict[str, Any]:
    return {
        "instance_id": instance_id,
        "state": _condition_state(outcome),
        "condition": outcome,
        "facts": facts,
        "group_id": group_id,
        "competing_rule_ids": [],
        "selected_rule_id": None,
        "decision_refs": [],
        "precedence_edge_ids": [],
    }


def _active_edges(rule_set: dict[str, Any], group: dict[str, Any]) -> list[dict[str, Any]]:
    if rule_set["rule_set"]["status"] != "adopted":
        return []
    active: list[dict[str, Any]] = []
    for edge in group["supersession"]:
        if edge["decision_ref"] is None:
            continue
        evidence = {
            "group_id": group["id"],
            "rule_id": edge["rule_id"],
            "supersedes": edge["supersedes"],
            "decision_ref": edge["decision_ref"],
            "source_refs": edge["source_refs"],
        }
        active.append({"id": canonical_hash(evidence), **evidence})
    return sorted(active, key=lambda item: item["id"])


def _precedence_paths(
    edges: list[dict[str, Any]],
) -> dict[tuple[str, str], tuple[str, ...]]:
    graph: dict[str, list[tuple[str, str]]] = {}
    nodes: set[str] = set()
    for edge in edges:
        winner = edge["rule_id"]
        loser = edge["supersedes"]
        graph.setdefault(winner, []).append((loser, edge["id"]))
        nodes.update((winner, loser))

    paths: dict[tuple[str, str], tuple[str, ...]] = {}
    for start in sorted(nodes):
        queue: deque[tuple[str, tuple[str, ...]]] = deque([(start, ())])
        visited: set[str] = set()
        while queue:
            node, edge_ids = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            paths[(start, node)] = edge_ids
            for child, edge_id in sorted(graph.get(node, [])):
                queue.append((child, edge_ids + (edge_id,)))
    return paths


def _unique_winner(
    active_rule_ids: list[str],
    paths: dict[tuple[str, str], tuple[str, ...]],
) -> tuple[str | None, list[str]]:
    winners: list[tuple[str, list[str]]] = []
    for candidate in sorted(active_rule_ids):
        edge_ids: set[str] = set()
        reaches_all = True
        for other in active_rule_ids:
            if candidate == other:
                continue
            path = paths.get((candidate, other))
            if path is None:
                reaches_all = False
                break
            edge_ids.update(path)
        if reaches_all:
            winners.append((candidate, sorted(edge_ids)))
    if len(winners) != 1:
        return None, []
    return winners[0]


def _resolution_record(
    *,
    instance_id: str,
    group_id: str,
    status: str,
    reason: str,
    selected_rule_id: str | None,
    competing_rule_ids: list[str],
    superseded_rule_ids: list[str],
    decision_refs: list[str],
    precedence_edge_ids: list[str],
) -> dict[str, Any]:
    return {
        "instance_id": instance_id,
        "group_id": group_id,
        "status": status,
        "reason": reason,
        "selected_rule_id": selected_rule_id,
        "competing_rule_ids": sorted(competing_rule_ids),
        "superseded_rule_ids": sorted(superseded_rule_ids),
        "decision_refs": sorted(decision_refs),
        "precedence_edge_ids": sorted(precedence_edge_ids),
    }


def _resolve_groups(
    rule_set: dict[str, Any],
    artifact: dict[str, Any],
    states: dict[str, dict[str, dict[str, Any]]],
    active_edges_by_group: dict[str, list[dict[str, Any]]],
    paths_by_group: dict[str, dict[tuple[str, str], tuple[str, ...]]],
) -> list[dict[str, Any]]:
    resolutions: list[dict[str, Any]] = []
    for group in sorted(rule_set["conflict_groups"], key=lambda item: item["id"]):
        members = sorted(group["members"])
        edges = active_edges_by_group[group["id"]]
        edge_by_id = {edge["id"]: edge for edge in edges}
        paths = paths_by_group[group["id"]]
        for instance in artifact["instances"]:
            instance_id = instance["id"]
            records = {
                member: states[member][instance_id]
                for member in members
                if instance_id in states[member]
            }
            if not records:
                continue
            true_ids = sorted(
                rule_id
                for rule_id, record in records.items()
                if record["state"] == "CONDITION_TRUE"
            )
            unresolved_ids = sorted(
                rule_id
                for rule_id, record in records.items()
                if record["state"] in {"UNKNOWN_FACT", "FACT_CONFLICT"}
            )
            if unresolved_ids:
                competing = sorted(set(true_ids + unresolved_ids))
                for rule_id in true_ids:
                    record = records[rule_id]
                    record["state"] = "RULE_CONFLICT"
                    record["competing_rule_ids"] = [item for item in competing if item != rule_id]
                for rule_id in unresolved_ids:
                    records[rule_id]["competing_rule_ids"] = [item for item in competing if item != rule_id]
                resolutions.append(
                    _resolution_record(
                        instance_id=instance_id,
                        group_id=group["id"],
                        status="REVIEW",
                        reason="unresolved_member",
                        selected_rule_id=None,
                        competing_rule_ids=competing,
                        superseded_rule_ids=[],
                        decision_refs=[],
                        precedence_edge_ids=[],
                    )
                )
                continue
            if not true_ids:
                continue
            if len(true_ids) == 1:
                resolutions.append(
                    _resolution_record(
                        instance_id=instance_id,
                        group_id=group["id"],
                        status="SELECTED",
                        reason="single_applicable_rule",
                        selected_rule_id=true_ids[0],
                        competing_rule_ids=true_ids,
                        superseded_rule_ids=[],
                        decision_refs=[],
                        precedence_edge_ids=[],
                    )
                )
                continue
            winner, precedence_edge_ids = _unique_winner(true_ids, paths)
            if winner is None:
                for rule_id in true_ids:
                    record = records[rule_id]
                    record["state"] = "RULE_CONFLICT"
                    record["competing_rule_ids"] = [item for item in true_ids if item != rule_id]
                resolutions.append(
                    _resolution_record(
                        instance_id=instance_id,
                        group_id=group["id"],
                        status="REVIEW",
                        reason="no_configured_winner",
                        selected_rule_id=None,
                        competing_rule_ids=true_ids,
                        superseded_rule_ids=[],
                        decision_refs=[],
                        precedence_edge_ids=[],
                    )
                )
                continue
            decision_refs = sorted(
                {edge_by_id[edge_id]["decision_ref"] for edge_id in precedence_edge_ids}
            )
            losers = [rule_id for rule_id in true_ids if rule_id != winner]
            for loser in losers:
                record = records[loser]
                record["state"] = "SUPERSEDED"
                record["selected_rule_id"] = winner
                record["decision_refs"] = decision_refs
                record["precedence_edge_ids"] = precedence_edge_ids
            resolutions.append(
                _resolution_record(
                    instance_id=instance_id,
                    group_id=group["id"],
                    status="SELECTED",
                    reason="configured_precedence",
                    selected_rule_id=winner,
                    competing_rule_ids=true_ids,
                    superseded_rule_ids=losers,
                    decision_refs=decision_refs,
                    precedence_edge_ids=precedence_edge_ids,
                )
            )
    return sorted(resolutions, key=lambda item: (item["instance_id"], item["group_id"]))


def _context_review_evidence(
    record: dict[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    reason_by_state = {
        "UNKNOWN_FACT": "missing_or_unaccepted_fact",
        "FACT_CONFLICT": "conflicting_fact_assertions",
        "RULE_CONFLICT": "unresolved_rule_conflict",
    }
    assertion_ids: set[str] = set()
    fact_ids: set[str] = set()
    for trace in record["facts"]:
        fact_ids.add(trace["fact"])
        assertion_ids.update(trace["accepted_assertion_ids"])
        assertion_ids.update(trace["unaccepted_assertion_ids"])
    return {
        "instance_id": record["instance_id"],
        "surface": surface,
        "reason": reason_by_state[record["state"]],
        "fact_ids": sorted(fact_ids),
        "assertion_ids": sorted(assertion_ids),
        "group_id": record["group_id"],
        "competing_rule_ids": record["competing_rule_ids"],
    }


def _filtered_artifact(
    artifact: dict[str, Any],
    active_ids: set[str],
) -> dict[str, Any]:
    return {
        "schema_version": "content-artifact/1",
        "instances": [
            {
                "id": instance["id"],
                "surface": instance["surface"],
                "fields": instance["fields"],
            }
            for instance in artifact["instances"]
            if instance["id"] in active_ids
        ],
    }


def _fact_counts(assertions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for assertion in assertions:
        fact_id = assertion["fact"]
        counts[fact_id] = counts.get(fact_id, 0) + 1
    return counts


def _preflight_receipt_detail(
    rule_set: dict[str, Any],
    artifact: dict[str, Any],
    rules_by_id: dict[str, dict[str, Any]],
    active_edges_by_group: dict[str, list[dict[str, Any]]],
) -> None:
    definitions = {
        definition["id"]: definition
        for definition in rule_set["fact_definitions"]
    }
    artifact_fact_counts = _fact_counts(artifact["facts"])
    instance_fact_counts = {
        instance["id"]: _fact_counts(instance["facts"])
        for instance in artifact["instances"]
    }
    matching_instances_by_rule = {
        rule_id: matching_instances(artifact, rule["scope"]["surfaces"])
        for rule_id, rule in rules_by_id.items()
    }
    evaluations = sum(len(instances) for instances in matching_instances_by_rule.values())
    if evaluations > MAX_RULE_INSTANCE_EVALUATIONS:
        raise RuleError(
            "EVALUATION_LIMIT",
            f"Contextual rule-instance evaluations exceed {MAX_RULE_INSTANCE_EVALUATIONS}",
        )
    matching_ids_by_rule: dict[str, set[str]] = {}
    trace_units = sum(len(edges) for edges in active_edges_by_group.values())
    contextual_rule_ids = {
        rule["id"]
        for rule in rule_set["rules"]
        if "applies_when" in rule
    } | {
        rule_id
        for group in rule_set["conflict_groups"]
        for rule_id in group["members"]
    }

    for rule_id in sorted(rules_by_id):
        rule = rules_by_id[rule_id]
        instances = matching_instances_by_rule[rule_id]
        matching_ids_by_rule[rule_id] = {instance["id"] for instance in instances}
        fields = rule["scope"]["fields"]
        target_units = sum(
            max(1, len(instance["fields"])) if fields == ["*"] else len(fields)
            for instance in instances
        )
        if rule["check"] == "banned_terms":
            evidence_upper = target_units * len(rule["params"]["terms"])
            review_upper = target_units
        elif rule["check"] == "required_terminology":
            evidence_upper = target_units * len(rule["params"]["instead_of"])
            review_upper = target_units
        elif rule["check"] == "character_limit":
            evidence_upper = target_units
            review_upper = target_units
        else:
            evidence_upper = len(instances)
            review_upper = len(instances)
        if rule_id in contextual_rule_ids:
            review_upper += len(instances)
        if max(evidence_upper, review_upper) > MAX_RECEIPT_EVIDENCE_ITEMS_PER_RESULT:
            raise RuleError(
                "RECEIPT_DETAIL_LIMIT",
                "A result could exceed the receipt's per-rule evidence limit of "
                f"{MAX_RECEIPT_EVIDENCE_ITEMS_PER_RESULT} items",
            )
        trace_units += evidence_upper + review_upper
        conditions = rule.get("applies_when", {}).get("all", [])
        for instance in instances:
            trace_units += 1
            for condition in conditions:
                definition = definitions[condition["fact"]]
                counts = (
                    artifact_fact_counts
                    if definition["level"] == "artifact"
                    else instance_fact_counts[instance["id"]]
                )
                trace_units += 1 + counts.get(condition["fact"], 0)
            if trace_units > MAX_RECEIPT_TRACE_UNITS:
                raise RuleError(
                    "RECEIPT_DETAIL_LIMIT",
                    f"Receipt detail exceeds {MAX_RECEIPT_TRACE_UNITS} bounded trace units",
                )

    for group in rule_set["conflict_groups"]:
        matching_group_instances: set[str] = set()
        for rule_id in group["members"]:
            matching_group_instances.update(matching_ids_by_rule[rule_id])
        trace_units += len(matching_group_instances) * (
            1 + len(active_edges_by_group[group["id"]])
        )
        if trace_units > MAX_RECEIPT_TRACE_UNITS:
            raise RuleError(
                "RECEIPT_DETAIL_LIMIT",
                f"Receipt detail exceeds {MAX_RECEIPT_TRACE_UNITS} bounded trace units",
            )


def _evaluate_rule(
    rule: dict[str, Any],
    artifact: dict[str, Any],
    records: dict[str, dict[str, Any]],
    evaluator: Any,
) -> dict[str, Any]:
    active_ids = {
        instance_id
        for instance_id, record in records.items()
        if record["state"] == "CONDITION_TRUE"
    }
    unresolved = [
        record
        for record in records.values()
        if record["state"] in {"UNKNOWN_FACT", "FACT_CONFLICT", "RULE_CONFLICT"}
    ]
    contextual_reviews = [
        _context_review_evidence(
            record,
            surface=next(
                instance["surface"]
                for instance in artifact["instances"]
                if instance["id"] == record["instance_id"]
            ),
        )
        for record in unresolved
    ]
    if active_ids:
        result = evaluator(rule, _filtered_artifact(artifact, active_ids))
        result["review_evidence"] = result["review_evidence"] + contextual_reviews
        if result["status"] != "FAIL" and contextual_reviews:
            result["status"] = "REVIEW"
            result["message"] = "The check ran where applicable, but contextual applicability remains unresolved."
    elif contextual_reviews:
        result = {
            **result_base(rule),
            "status": "REVIEW",
            "message": "Contextual applicability could not be resolved.",
            "evidence": [],
            "review_evidence": contextual_reviews,
        }
    else:
        result = {
            **result_base(rule),
            "status": "NOT_APPLICABLE",
            "message": "No artifact instance selected this rule after contextual resolution.",
            "evidence": [],
            "review_evidence": [],
        }
    matching_count = len(records)
    result["applicability"] = {
        "out_of_scope_count": len(artifact["instances"]) - matching_count,
        "source_refs": rule.get("applies_when", {}).get("source_refs", []),
        "instances": [records[instance_id] for instance_id in sorted(records)],
    }
    return result


def run_checks_v2(
    rule_set: dict[str, Any],
    artifact: dict[str, Any],
    *,
    evaluators: dict[str, Any],
    rules_path: Path,
    artifact_path: Path,
    rules_sha256: str,
    artifact_sha256: str,
    verified_sources: list[dict[str, str]],
) -> dict[str, Any]:
    rules_by_id = {rule["id"]: rule for rule in rule_set["rules"]}
    active_edges_by_group = {
        group["id"]: _active_edges(rule_set, group)
        for group in rule_set["conflict_groups"]
    }
    paths_by_group = {
        group_id: _precedence_paths(edges)
        for group_id, edges in active_edges_by_group.items()
    }
    precedence_evidence = sorted(
        (
            edge
            for edges in active_edges_by_group.values()
            for edge in edges
        ),
        key=lambda item: item["id"],
    )
    _preflight_receipt_detail(
        rule_set,
        artifact,
        rules_by_id,
        active_edges_by_group,
    )
    membership = {
        rule_id: group["id"]
        for group in rule_set["conflict_groups"]
        for rule_id in group["members"]
    }
    states: dict[str, dict[str, dict[str, Any]]] = {
        rule_id: {} for rule_id in rules_by_id
    }
    for rule_id in sorted(rules_by_id):
        rule = rules_by_id[rule_id]
        for instance in matching_instances(artifact, rule["scope"]["surfaces"]):
            outcome, traces = evaluate_applicability(
                rule,
                rule_set=rule_set,
                artifact=artifact,
                instance=instance,
            )
            states[rule_id][instance["id"]] = _applicability_record(
                instance_id=instance["id"],
                outcome=outcome,
                facts=traces,
                group_id=membership.get(rule_id),
            )

    resolutions = _resolve_groups(
        rule_set,
        artifact,
        states,
        active_edges_by_group,
        paths_by_group,
    )
    results = [
        _evaluate_rule(
            rules_by_id[rule_id],
            artifact,
            states[rule_id],
            evaluators[rules_by_id[rule_id]["check"]],
        )
        for rule_id in sorted(rules_by_id)
    ]
    statuses = ("PASS", "FAIL", "REVIEW", "NOT_APPLICABLE")
    counts = {status: sum(result["status"] == status for result in results) for status in statuses}
    if counts["FAIL"]:
        aggregate = "FAIL"
    elif counts["REVIEW"]:
        aggregate = "REVIEW"
    elif counts["PASS"]:
        aggregate = "PASS"
    else:
        aggregate = "NOT_APPLICABLE"
    unresolved_applicability = sum(
        record["state"] in {"UNKNOWN_FACT", "FACT_CONFLICT", "RULE_CONFLICT"}
        for rule_states in states.values()
        for record in rule_states.values()
    )
    metadata = rule_set["rule_set"]
    fact_assertion_count = len(artifact["facts"]) + sum(
        len(instance["facts"]) for instance in artifact["instances"]
    )
    receipt = {
        "protocol": RECEIPT_PROTOCOL_V2,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "rule_set": {
            "id": metadata["id"],
            "name": metadata["name"],
            "status": metadata["status"],
            "owner": metadata["owner"],
            "decision_ref": metadata["decision_ref"],
            "effect": "check result only; the calling workflow decides consequences",
            "authority_note": (
                "Adoption, precedence, and fact-provider provenance are recorded claims; "
                "this runtime does not authenticate them. Trusted host-controlled adapters must supply facts."
            ),
            "path": rules_path.name,
            "sha256": rules_sha256,
            "canonical_sha256": canonical_hash(rule_set),
            "fact_definition_count": len(rule_set["fact_definitions"]),
            "conflict_group_count": len(rule_set["conflict_groups"]),
        },
        "sources": verified_sources,
        "artifact": {
            "path": artifact_path.name,
            "sha256": artifact_sha256,
            "canonical_sha256": canonical_hash(artifact),
            "instance_count": len(artifact["instances"]),
            "fact_assertion_count": fact_assertion_count,
        },
        "summary": {
            "status": aggregate,
            "applicable": counts["PASS"] + counts["FAIL"] + counts["REVIEW"],
            "passed": counts["PASS"],
            "failed": counts["FAIL"],
            "review": counts["REVIEW"],
            "unresolved_evidence": sum(len(result["review_evidence"]) for result in results),
            "unresolved_applicability": unresolved_applicability,
            "not_applicable": counts["NOT_APPLICABLE"],
        },
        "precedence_evidence": precedence_evidence,
        "resolutions": resolutions,
        "results": results,
    }
    receipt_size = len(canonical_json(receipt).encode("utf-8"))
    if receipt_size > MAX_RECEIPT_BYTES:
        raise RuleError(
            "RECEIPT_SIZE_LIMIT",
            f"Receipt exceeds the {MAX_RECEIPT_BYTES // (1024 * 1024)} MB output limit",
        )
    return receipt
