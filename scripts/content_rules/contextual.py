from __future__ import annotations

import unicodedata
from collections.abc import Iterator
from typing import Any

from .common import (
    ARTIFACT_PROTOCOL,
    ARTIFACT_PROTOCOL_V2,
    CHECK_TYPES,
    ID_PATTERN,
    MAX_INSTANCES,
    MAX_FACT_ASSERTIONS,
    MAX_FACT_DEFINITIONS,
    MAX_RULES,
    MAX_RULE_INSTANCE_EVALUATIONS,
    MAX_SOURCES,
    MAX_SOURCE_REFS_PER_RULE,
    MAX_TOTAL_TERM_ENTRIES,
    RULE_SET_PROTOCOL,
    RULE_SET_PROTOCOL_V2,
    SHA256_PATTERN,
    RuleError,
    _contains_unresolved_template,
    _identifier,
    _list,
    _nonempty_string,
    _object,
    _reject_unknown,
    _relative_source_path,
    _scope_overlap,
    _string_list,
    _validate_rule_set_v1,
    canonical_hash,
)


MAX_ARTIFACT_FACTS = MAX_FACT_ASSERTIONS
MAX_INSTANCE_FACTS = 50
MAX_TOTAL_FACT_ASSERTIONS = 5_000
MAX_ACCEPTED_SOURCES = 20
MAX_ALLOWED_VALUES = 100
MAX_CONDITIONS_PER_RULE = 20
MAX_CONFLICT_GROUPS = 100
MAX_GROUP_MEMBERS = 50
MAX_SUPERSESSION_EDGES = 500
MAX_FACT_STRING_LENGTH = 500
MIN_FACT_INTEGER = -1_000_000_000
MAX_FACT_INTEGER = 1_000_000_000
FACT_TYPES = {"string", "boolean", "integer"}
ASSERTION_BASES = {"observed", "declared", "derived", "inferred"}
ACCEPTED_BASES = ASSERTION_BASES - {"inferred"}
CONDITION_OPERATORS = {"equals", "not_equals", "one_of"}


def _scalar_type(value: Any) -> str | None:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, str):
        return "string"
    return None


def _validate_scalar(
    value: Any,
    label: str,
    expected_type: str | None = None,
    *,
    error_code: str = "INVALID_CONFIG",
) -> Any:
    actual_type = _scalar_type(value)
    if actual_type is None:
        raise RuleError(error_code, f"{label} must be a string, boolean, or integer")
    if expected_type is not None and actual_type != expected_type:
        raise RuleError(error_code, f"{label} must have type {expected_type!r}")
    if actual_type == "string":
        if not value.strip():
            raise RuleError(error_code, f"{label} must be a non-empty string")
        if len(value) > MAX_FACT_STRING_LENGTH:
            raise RuleError(
                error_code,
                f"{label} exceeds {MAX_FACT_STRING_LENGTH} characters",
            )
    elif actual_type == "integer" and not MIN_FACT_INTEGER <= value <= MAX_FACT_INTEGER:
        raise RuleError(
            error_code,
            f"{label} must be from {MIN_FACT_INTEGER} to {MAX_FACT_INTEGER}",
        )
    return value


def _artifact_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuleError("INVALID_ARTIFACT", f"{label} must be a JSON object")
    return value


def _artifact_reject_unknown(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise RuleError(
            "INVALID_ARTIFACT",
            f"{label} has unknown field(s): {', '.join(unknown)}",
        )


def _typed_value_key(value: Any) -> tuple[str, Any]:
    value_type = _scalar_type(value)
    if value_type is None:
        raise AssertionError("validated fact values must be scalar")
    return value_type, value


def _validate_source_ref(
    ref_value: Any,
    *,
    label: str,
    source_ids: set[str],
) -> dict[str, Any]:
    ref = _object(ref_value, label)
    _reject_unknown(ref, {"source_id", "line_start", "line_end", "quote"}, label)
    source_id = _identifier(ref.get("source_id"), f"{label}.source_id")
    if source_id not in source_ids:
        raise RuleError("INVALID_CONFIG", f"{label} references unknown source: {source_id}")
    line_start = ref.get("line_start")
    line_end = ref.get("line_end")
    if not isinstance(line_start, int) or isinstance(line_start, bool) or line_start < 1:
        raise RuleError("INVALID_CONFIG", f"{label}.line_start must be a positive integer")
    if not isinstance(line_end, int) or isinstance(line_end, bool) or line_end < line_start:
        raise RuleError("INVALID_CONFIG", f"{label}.line_end must be at least line_start")
    _nonempty_string(ref.get("quote"), f"{label}.quote", 1000)
    return ref


def _validate_source_refs(
    value: Any,
    *,
    label: str,
    source_ids: set[str],
) -> list[dict[str, Any]]:
    refs = _list(value, label)
    if not refs:
        raise RuleError("INVALID_CONFIG", f"{label} must not be empty")
    if len(refs) > MAX_SOURCE_REFS_PER_RULE:
        raise RuleError(
            "INVALID_CONFIG",
            f"{label} exceeds {MAX_SOURCE_REFS_PER_RULE} items",
        )
    return [
        _validate_source_ref(ref, label=f"{label}[{index}]", source_ids=source_ids)
        for index, ref in enumerate(refs)
    ]


def _validate_metadata(metadata_value: Any) -> dict[str, Any]:
    metadata = _object(metadata_value, "rule_set")
    _reject_unknown(metadata, {"id", "name", "status", "owner", "decision_ref"}, "rule_set")
    _identifier(metadata.get("id"), "rule_set.id")
    _nonempty_string(metadata.get("name"), "rule_set.name", 120)
    status = metadata.get("status")
    if status not in {"proposed", "adopted"}:
        raise RuleError("INVALID_CONFIG", "rule_set.status must be 'proposed' or 'adopted'")
    if status == "adopted":
        _nonempty_string(metadata.get("owner"), "rule_set.owner", 120)
        _nonempty_string(metadata.get("decision_ref"), "rule_set.decision_ref", 300)
    elif metadata.get("owner") is not None or metadata.get("decision_ref") is not None:
        raise RuleError("INVALID_CONFIG", "proposed rule sets must use null owner and decision_ref")
    return metadata


def _validate_sources(sources_value: Any) -> tuple[list[dict[str, Any]], set[str]]:
    sources = _list(sources_value, "sources")
    if len(sources) > MAX_SOURCES:
        raise RuleError("INVALID_CONFIG", f"sources exceeds {MAX_SOURCES} items")
    source_ids: set[str] = set()
    for index, source_value in enumerate(sources):
        label = f"sources[{index}]"
        source = _object(source_value, label)
        _reject_unknown(source, {"id", "path", "sha256"}, label)
        source_id = _identifier(source.get("id"), f"{label}.id")
        if source_id in source_ids:
            raise RuleError("INVALID_CONFIG", f"Duplicate source id: {source_id}")
        source_ids.add(source_id)
        _relative_source_path(source.get("path"), f"{label}.path")
        sha = source.get("sha256")
        if not isinstance(sha, str) or not SHA256_PATTERN.fullmatch(sha):
            raise RuleError("INVALID_CONFIG", f"{label}.sha256 must be a lowercase SHA-256")
        if sha == "0" * 64:
            raise RuleError("UNRESOLVED_TEMPLATE", f"{label}.sha256 is still the template placeholder")
    return sources, source_ids


def _validate_fact_definitions(
    definitions_value: Any,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    definitions = _list(definitions_value, "fact_definitions")
    if len(definitions) > MAX_FACT_DEFINITIONS:
        raise RuleError(
            "INVALID_CONFIG",
            f"fact_definitions exceeds {MAX_FACT_DEFINITIONS} items",
        )
    by_id: dict[str, dict[str, Any]] = {}
    for index, definition_value in enumerate(definitions):
        label = f"fact_definitions[{index}]"
        definition = _object(definition_value, label)
        _reject_unknown(
            definition,
            {"id", "description", "level", "type", "allowed_values", "accepted_sources"},
            label,
        )
        fact_id = _identifier(definition.get("id"), f"{label}.id")
        if fact_id in by_id:
            raise RuleError("INVALID_CONFIG", f"Duplicate fact definition id: {fact_id}")
        _nonempty_string(definition.get("description"), f"{label}.description", 300)
        if definition.get("level") not in {"artifact", "instance"}:
            raise RuleError("INVALID_CONFIG", f"{label}.level must be 'artifact' or 'instance'")
        fact_type = definition.get("type")
        if fact_type not in FACT_TYPES:
            raise RuleError("INVALID_CONFIG", f"{label}.type is unsupported: {fact_type!r}")

        allowed_values = definition.get("allowed_values")
        if allowed_values is not None:
            values = _list(allowed_values, f"{label}.allowed_values")
            if not values:
                raise RuleError("INVALID_CONFIG", f"{label}.allowed_values must not be empty")
            if len(values) > MAX_ALLOWED_VALUES:
                raise RuleError(
                    "INVALID_CONFIG",
                    f"{label}.allowed_values exceeds {MAX_ALLOWED_VALUES} items",
                )
            seen_values: set[tuple[str, Any]] = set()
            for value_index, value in enumerate(values):
                _validate_scalar(value, f"{label}.allowed_values[{value_index}]", fact_type)
                key = _typed_value_key(value)
                if key in seen_values:
                    raise RuleError("INVALID_CONFIG", f"{label}.allowed_values contains a duplicate")
                seen_values.add(key)

        accepted = _list(definition.get("accepted_sources"), f"{label}.accepted_sources")
        if not accepted:
            raise RuleError("INVALID_CONFIG", f"{label}.accepted_sources must not be empty")
        if len(accepted) > MAX_ACCEPTED_SOURCES:
            raise RuleError(
                "INVALID_CONFIG",
                f"{label}.accepted_sources exceeds {MAX_ACCEPTED_SOURCES} items",
            )
        accepted_pairs: set[tuple[str, str]] = set()
        for source_index, source_value in enumerate(accepted):
            source_label = f"{label}.accepted_sources[{source_index}]"
            source = _object(source_value, source_label)
            _reject_unknown(source, {"basis", "provider"}, source_label)
            basis = source.get("basis")
            if basis not in ACCEPTED_BASES:
                raise RuleError(
                    "INVALID_CONFIG",
                    f"{source_label}.basis must be observed, declared, or derived",
                )
            provider = _identifier(source.get("provider"), f"{source_label}.provider")
            pair = (basis, provider)
            if pair in accepted_pairs:
                raise RuleError("INVALID_CONFIG", f"{label}.accepted_sources contains a duplicate")
            accepted_pairs.add(pair)
        by_id[fact_id] = definition
    return definitions, by_id


def _validate_condition(
    condition_value: Any,
    *,
    label: str,
    fact_definitions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    condition = _object(condition_value, label)
    op = condition.get("op")
    if op not in CONDITION_OPERATORS:
        raise RuleError("INVALID_CONFIG", f"{label}.op is unsupported: {op!r}")
    fact_id = _identifier(condition.get("fact"), f"{label}.fact")
    if fact_id not in fact_definitions:
        raise RuleError("INVALID_CONFIG", f"{label} references unknown fact: {fact_id}")
    definition = fact_definitions[fact_id]
    if op == "one_of":
        _reject_unknown(condition, {"fact", "op", "values"}, label)
        values = _list(condition.get("values"), f"{label}.values")
        if not values:
            raise RuleError("INVALID_CONFIG", f"{label}.values must not be empty")
        if len(values) > 50:
            raise RuleError("INVALID_CONFIG", f"{label}.values exceeds 50 items")
        seen: set[tuple[str, Any]] = set()
        for index, value in enumerate(values):
            _validate_fact_expected_value(value, definition, f"{label}.values[{index}]")
            key = _typed_value_key(value)
            if key in seen:
                raise RuleError("INVALID_CONFIG", f"{label}.values contains a duplicate")
            seen.add(key)
    else:
        _reject_unknown(condition, {"fact", "op", "value"}, label)
        _validate_fact_expected_value(condition.get("value"), definition, f"{label}.value")
    return condition


def _validate_fact_expected_value(value: Any, definition: dict[str, Any], label: str) -> None:
    _validate_scalar(value, label, definition["type"])
    allowed = definition.get("allowed_values")
    if allowed is not None and _typed_value_key(value) not in {
        _typed_value_key(item) for item in allowed
    }:
        raise RuleError("INVALID_CONFIG", f"{label} is outside the fact definition's allowed_values")


def _base_rule_for_v1(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        key: rule[key]
        for key in ("id", "description", "check", "scope", "params", "source_refs")
    }


def _validate_rules(
    rules_value: Any,
    *,
    metadata: dict[str, Any],
    sources: list[dict[str, Any]],
    source_ids: set[str],
    fact_definitions: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rules = _list(rules_value, "rules")
    if len(rules) > MAX_RULES:
        raise RuleError("INVALID_CONFIG", f"rules exceeds {MAX_RULES} items")
    by_id: dict[str, dict[str, Any]] = {}
    total_term_entries = 0
    for index, rule_value in enumerate(rules):
        label = f"rules[{index}]"
        rule = _object(rule_value, label)
        _reject_unknown(
            rule,
            {"id", "description", "check", "scope", "params", "source_refs", "applies_when"},
            label,
        )
        rule_id = _identifier(rule.get("id"), f"{label}.id")
        if rule_id in by_id:
            raise RuleError("INVALID_CONFIG", f"Duplicate rule id: {rule_id}")
        if rule.get("check") not in CHECK_TYPES:
            raise RuleError("INVALID_CONFIG", f"{label}.check is unsupported: {rule.get('check')!r}")

        v1_document = {
            "schema_version": RULE_SET_PROTOCOL,
            "rule_set": metadata,
            "sources": sources,
            "rules": [_base_rule_for_v1(rule)],
        }
        _validate_rule_set_v1(v1_document)

        if rule["check"] == "banned_terms":
            total_term_entries += len(rule["params"]["terms"])
        elif rule["check"] == "required_terminology":
            total_term_entries += len(rule["params"]["instead_of"]) + 1
        if total_term_entries > MAX_TOTAL_TERM_ENTRIES:
            raise RuleError(
                "INVALID_CONFIG",
                f"Configured term entries exceed {MAX_TOTAL_TERM_ENTRIES}",
            )

        applies_when = rule.get("applies_when")
        if applies_when is not None:
            applicability = _object(applies_when, f"{label}.applies_when")
            _reject_unknown(applicability, {"all", "source_refs"}, f"{label}.applies_when")
            conditions = _list(applicability.get("all"), f"{label}.applies_when.all")
            if not conditions:
                raise RuleError("INVALID_CONFIG", f"{label}.applies_when.all must not be empty")
            if len(conditions) > MAX_CONDITIONS_PER_RULE:
                raise RuleError(
                    "INVALID_CONFIG",
                    f"{label}.applies_when.all exceeds {MAX_CONDITIONS_PER_RULE} items",
                )
            seen_conditions: set[str] = set()
            conditioned_facts: set[str] = set()
            for condition_index, condition in enumerate(conditions):
                validated = _validate_condition(
                    condition,
                    label=f"{label}.applies_when.all[{condition_index}]",
                    fact_definitions=fact_definitions,
                )
                fact_id = validated["fact"]
                if fact_id in conditioned_facts:
                    raise RuleError(
                        "INVALID_CONFIG",
                        f"{label}.applies_when may contain only one condition for fact {fact_id!r}",
                    )
                conditioned_facts.add(fact_id)
                key = canonical_hash(validated)
                if key in seen_conditions:
                    raise RuleError("INVALID_CONFIG", f"{label}.applies_when.all contains a duplicate")
                seen_conditions.add(key)
            _validate_source_refs(
                applicability.get("source_refs"),
                label=f"{label}.applies_when.source_refs",
                source_ids=source_ids,
            )
        by_id[rule_id] = rule
    return rules, by_id


def _surfaces_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return _scope_overlap(left["scope"], right["scope"])


def _validate_acyclic(edges: list[tuple[str, str]], *, group_id: str) -> None:
    graph: dict[str, set[str]] = {}
    for winner, loser in edges:
        graph.setdefault(winner, set()).add(loser)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise RuleError("INVALID_CONFIG", f"Conflict group {group_id} contains a supersession cycle")
        if node in visited:
            return
        visiting.add(node)
        for child in sorted(graph.get(node, set())):
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        visit(node)


def _validate_conflict_groups(
    groups_value: Any,
    *,
    metadata: dict[str, Any],
    rules: dict[str, dict[str, Any]],
    source_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    groups = _list(groups_value, "conflict_groups")
    if len(groups) > MAX_CONFLICT_GROUPS:
        raise RuleError(
            "INVALID_CONFIG",
            f"conflict_groups exceeds {MAX_CONFLICT_GROUPS} items",
        )
    seen_groups: set[str] = set()
    membership: dict[str, str] = {}
    total_edges = 0
    for index, group_value in enumerate(groups):
        label = f"conflict_groups[{index}]"
        group = _object(group_value, label)
        _reject_unknown(group, {"id", "description", "members", "supersession"}, label)
        group_id = _identifier(group.get("id"), f"{label}.id")
        if group_id in seen_groups:
            raise RuleError("INVALID_CONFIG", f"Duplicate conflict group id: {group_id}")
        seen_groups.add(group_id)
        _nonempty_string(group.get("description"), f"{label}.description", 300)
        members = _string_list(
            group.get("members"),
            f"{label}.members",
            maximum_items=MAX_GROUP_MEMBERS,
        )
        if len(members) < 2:
            raise RuleError("INVALID_CONFIG", f"{label}.members must contain at least two rules")
        for member in members:
            if member not in rules:
                raise RuleError("INVALID_CONFIG", f"{label}.members references unknown rule: {member}")
            if member in membership:
                raise RuleError(
                    "INVALID_CONFIG",
                    f"Rule {member} belongs to more than one conflict group",
                )
            membership[member] = group_id
        first = rules[members[0]]
        for member in members[1:]:
            candidate = rules[member]
            if candidate["check"] != first["check"]:
                raise RuleError("INVALID_CONFIG", f"{label}.members must use the same checker")
            if candidate["scope"]["fields"] != first["scope"]["fields"]:
                raise RuleError("INVALID_CONFIG", f"{label}.members must use exactly the same field scope")

        supersession = _list(group.get("supersession"), f"{label}.supersession")
        total_edges += len(supersession)
        if total_edges > MAX_SUPERSESSION_EDGES:
            raise RuleError(
                "INVALID_CONFIG",
                f"supersession edges exceed {MAX_SUPERSESSION_EDGES}",
            )
        seen_edges: set[tuple[str, str]] = set()
        graph_edges: list[tuple[str, str]] = []
        for edge_index, edge_value in enumerate(supersession):
            edge_label = f"{label}.supersession[{edge_index}]"
            edge = _object(edge_value, edge_label)
            _reject_unknown(
                edge,
                {"rule_id", "supersedes", "decision_ref", "source_refs"},
                edge_label,
            )
            winner = _identifier(edge.get("rule_id"), f"{edge_label}.rule_id")
            loser = _identifier(edge.get("supersedes"), f"{edge_label}.supersedes")
            if winner not in members or loser not in members:
                raise RuleError("INVALID_CONFIG", f"{edge_label} must reference members of {group_id}")
            if winner == loser:
                raise RuleError("INVALID_CONFIG", f"{edge_label} cannot supersede itself")
            pair = (winner, loser)
            if pair in seen_edges:
                raise RuleError("INVALID_CONFIG", f"{label}.supersession contains a duplicate edge")
            seen_edges.add(pair)
            graph_edges.append(pair)
            if not _surfaces_overlap(rules[winner], rules[loser]):
                raise RuleError("INVALID_CONFIG", f"{edge_label} connects rules with disjoint scopes")
            decision_ref = edge.get("decision_ref")
            if metadata["status"] == "adopted":
                _nonempty_string(decision_ref, f"{edge_label}.decision_ref", 300)
            elif decision_ref is not None:
                raise RuleError(
                    "INVALID_CONFIG",
                    f"{edge_label}.decision_ref must be null while the rule set is proposed",
                )
            _validate_source_refs(
                edge.get("source_refs"),
                label=f"{edge_label}.source_refs",
                source_ids=source_ids,
            )
        _validate_acyclic(graph_edges, group_id=group_id)
    return groups, membership


def _validate_v2_terminology_conflicts(
    rules: list[dict[str, Any]],
    membership: dict[str, str],
) -> None:
    targets: list[tuple[dict[str, Any], str, str, bool]] = []
    for rule in rules:
        if rule["check"] != "required_terminology":
            continue
        params = rule["params"]
        for variant in params["instead_of"]:
            targets.append(
                (
                    rule,
                    unicodedata.normalize("NFC", variant),
                    unicodedata.normalize("NFC", params["preferred"]),
                    params["case_sensitive"],
                )
            )
    for index, (left, left_variant, left_preferred, left_case) in enumerate(targets):
        for right, right_variant, right_preferred, right_case in targets[index + 1 :]:
            if not _scope_overlap(left["scope"], right["scope"]):
                continue
            variants_overlap = (
                left_variant == right_variant
                if left_case and right_case
                else left_variant.casefold() == right_variant.casefold()
            )
            preferred_agrees = (
                left_preferred == right_preferred
                if left_case and right_case
                else left_preferred.casefold() == right_preferred.casefold()
            )
            if not variants_overlap or preferred_agrees:
                continue
            if membership.get(left["id"]) != membership.get(right["id"]) or left["id"] not in membership:
                raise RuleError(
                    "INVALID_CONFIG",
                    "Conflicting required_terminology mappings require one explicit conflict group",
                )


def validate_rule_set_v2(raw: Any) -> dict[str, Any]:
    document = _object(raw, "rule set")
    if _contains_unresolved_template(document):
        raise RuleError("UNRESOLVED_TEMPLATE", "Rule set still contains __REPLACE_ME__ template values")
    _reject_unknown(
        document,
        {"schema_version", "rule_set", "sources", "fact_definitions", "rules", "conflict_groups"},
        "rule set",
    )
    if document.get("schema_version") != RULE_SET_PROTOCOL_V2:
        raise RuleError("INVALID_CONFIG", f"schema_version must be {RULE_SET_PROTOCOL_V2!r}")
    metadata = _validate_metadata(document.get("rule_set"))
    sources, source_ids = _validate_sources(document.get("sources"))
    _, fact_definitions = _validate_fact_definitions(document.get("fact_definitions"))
    rules, rules_by_id = _validate_rules(
        document.get("rules"),
        metadata=metadata,
        sources=sources,
        source_ids=source_ids,
        fact_definitions=fact_definitions,
    )
    _, membership = _validate_conflict_groups(
        document.get("conflict_groups"),
        metadata=metadata,
        rules=rules_by_id,
        source_ids=source_ids,
    )
    _validate_v2_terminology_conflicts(rules, membership)
    return document


def _validate_assertion(value: Any, *, label: str) -> dict[str, Any]:
    assertion = _artifact_object(value, label)
    _artifact_reject_unknown(assertion, {"id", "fact", "value", "provenance"}, label)
    for key in ("id", "fact"):
        identifier = assertion.get(key)
        if not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier):
            raise RuleError("INVALID_ARTIFACT", f"{label}.{key} must be a lowercase identifier")
    _validate_scalar(assertion.get("value"), f"{label}.value", error_code="INVALID_ARTIFACT")
    provenance = _artifact_object(assertion.get("provenance"), f"{label}.provenance")
    _artifact_reject_unknown(provenance, {"basis", "provider", "ref"}, f"{label}.provenance")
    if provenance.get("basis") not in ASSERTION_BASES:
        raise RuleError("INVALID_ARTIFACT", f"{label}.provenance.basis is unsupported")
    provider = provenance.get("provider")
    if not isinstance(provider, str) or not ID_PATTERN.fullmatch(provider):
        raise RuleError("INVALID_ARTIFACT", f"{label}.provenance.provider must be a lowercase identifier")
    reference = provenance.get("ref")
    if not isinstance(reference, str) or not reference.strip() or len(reference) > 300:
        raise RuleError("INVALID_ARTIFACT", f"{label}.provenance.ref must be a non-empty string")
    return assertion


def validate_artifact_v2(raw: Any) -> dict[str, Any]:
    artifact = _artifact_object(raw, "artifact")
    _artifact_reject_unknown(artifact, {"schema_version", "facts", "instances"}, "artifact")
    if artifact.get("schema_version") != ARTIFACT_PROTOCOL_V2:
        raise RuleError("INVALID_ARTIFACT", f"artifact.schema_version must be {ARTIFACT_PROTOCOL_V2!r}")
    top_facts = artifact.get("facts")
    if not isinstance(top_facts, list):
        raise RuleError("INVALID_ARTIFACT", "artifact.facts must be a JSON array")
    if len(top_facts) > MAX_ARTIFACT_FACTS:
        raise RuleError("INVALID_ARTIFACT", f"artifact.facts exceeds {MAX_ARTIFACT_FACTS} items")
    assertion_ids: set[str] = set()
    total_assertions = 0
    for index, assertion_value in enumerate(top_facts):
        assertion = _validate_assertion(assertion_value, label=f"artifact.facts[{index}]")
        if assertion["id"] in assertion_ids:
            raise RuleError("INVALID_ARTIFACT", f"Duplicate fact assertion id: {assertion['id']}")
        assertion_ids.add(assertion["id"])
        total_assertions += 1

    instances = artifact.get("instances")
    if not isinstance(instances, list):
        raise RuleError("INVALID_ARTIFACT", "artifact.instances must be a JSON array")
    if len(instances) > MAX_INSTANCES:
        raise RuleError("INVALID_ARTIFACT", f"artifact.instances exceeds {MAX_INSTANCES} items")
    instance_ids: set[str] = set()
    for index, instance_value in enumerate(instances):
        label = f"artifact.instances[{index}]"
        instance = _artifact_object(instance_value, label)
        _artifact_reject_unknown(instance, {"id", "surface", "fields", "facts"}, label)
        instance_id = instance.get("id")
        if not isinstance(instance_id, str) or not ID_PATTERN.fullmatch(instance_id):
            raise RuleError("INVALID_ARTIFACT", f"{label}.id must be a lowercase identifier")
        if instance_id in instance_ids:
            raise RuleError("INVALID_ARTIFACT", f"Duplicate artifact instance id: {instance_id}")
        instance_ids.add(instance_id)
        surface = instance.get("surface")
        if not isinstance(surface, str) or not surface.strip() or len(surface) > 120:
            raise RuleError("INVALID_ARTIFACT", f"{label}.surface must be a non-empty string")
        fields = instance.get("fields")
        if not isinstance(fields, dict):
            raise RuleError("INVALID_ARTIFACT", f"{label}.fields must be a JSON object")
        if len(fields) > 200:
            raise RuleError("INVALID_ARTIFACT", f"{label}.fields exceeds 200 fields")
        for field_name in fields:
            if not isinstance(field_name, str) or not field_name.strip() or len(field_name) > 120:
                raise RuleError("INVALID_ARTIFACT", f"{label}.fields has an invalid field name")
        facts = instance.get("facts")
        if not isinstance(facts, list):
            raise RuleError("INVALID_ARTIFACT", f"{label}.facts must be a JSON array")
        if len(facts) > MAX_INSTANCE_FACTS:
            raise RuleError("INVALID_ARTIFACT", f"{label}.facts exceeds {MAX_INSTANCE_FACTS} items")
        for fact_index, assertion_value in enumerate(facts):
            assertion = _validate_assertion(assertion_value, label=f"{label}.facts[{fact_index}]")
            if assertion["id"] in assertion_ids:
                raise RuleError("INVALID_ARTIFACT", f"Duplicate fact assertion id: {assertion['id']}")
            assertion_ids.add(assertion["id"])
            total_assertions += 1
            if total_assertions > MAX_TOTAL_FACT_ASSERTIONS:
                raise RuleError(
                    "INVALID_ARTIFACT",
                    f"fact assertions exceed {MAX_TOTAL_FACT_ASSERTIONS}",
                )
    return artifact


def validate_protocol_pair(rule_set: dict[str, Any], artifact: dict[str, Any]) -> None:
    pair = (rule_set["schema_version"], artifact["schema_version"])
    if pair not in {
        (RULE_SET_PROTOCOL, ARTIFACT_PROTOCOL),
        (RULE_SET_PROTOCOL_V2, ARTIFACT_PROTOCOL_V2),
    }:
        raise RuleError(
            "INCOMPATIBLE_PROTOCOLS",
            "Rule-set and artifact schema versions must both be /1 or both be /2",
        )


def _definition_map(rule_set: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {definition["id"]: definition for definition in rule_set["fact_definitions"]}


def validate_artifact_bindings(rule_set: dict[str, Any], artifact: dict[str, Any]) -> None:
    validate_protocol_pair(rule_set, artifact)
    if rule_set["schema_version"] != RULE_SET_PROTOCOL_V2:
        return
    definitions = _definition_map(rule_set)

    def validate_bound_assertion(assertion: dict[str, Any], expected_level: str, label: str) -> None:
        fact_id = assertion["fact"]
        if fact_id not in definitions:
            raise RuleError("INVALID_ARTIFACT", f"{label} references undefined fact: {fact_id}")
        definition = definitions[fact_id]
        if definition["level"] != expected_level:
            raise RuleError(
                "INVALID_ARTIFACT",
                f"{label} supplies {fact_id} at {expected_level} level; definition requires {definition['level']}",
            )
        value = assertion["value"]
        try:
            _validate_scalar(value, f"{label}.value", definition["type"])
        except RuleError as exc:
            raise RuleError("INVALID_ARTIFACT", exc.message) from exc
        allowed = definition.get("allowed_values")
        if allowed is not None and _typed_value_key(value) not in {
            _typed_value_key(item) for item in allowed
        }:
            raise RuleError(
                "INVALID_ARTIFACT",
                f"{label}.value is outside {fact_id}.allowed_values",
            )

    for index, assertion in enumerate(artifact["facts"]):
        validate_bound_assertion(assertion, "artifact", f"artifact.facts[{index}]")
    for instance_index, instance in enumerate(artifact["instances"]):
        for fact_index, assertion in enumerate(instance["facts"]):
            validate_bound_assertion(
                assertion,
                "instance",
                f"artifact.instances[{instance_index}].facts[{fact_index}]",
            )


def iter_source_refs_v2(rule_set: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    for rule in rule_set["rules"]:
        for ref in rule["source_refs"]:
            yield f"Rule {rule['id']}", ref
        if "applies_when" in rule:
            for ref in rule["applies_when"]["source_refs"]:
                yield f"Applicability for rule {rule['id']}", ref
    for group in rule_set["conflict_groups"]:
        for edge in group["supersession"]:
            for ref in edge["source_refs"]:
                yield (
                    f"Supersession {edge['rule_id']} over {edge['supersedes']} in {group['id']}",
                    ref,
                )


def _accepted_assertions(
    definition: dict[str, Any],
    assertions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted_sources = {
        (item["basis"], item["provider"])
        for item in definition["accepted_sources"]
    }
    accepted: list[dict[str, Any]] = []
    unaccepted: list[dict[str, Any]] = []
    for assertion in assertions:
        provenance = assertion["provenance"]
        pair = (provenance["basis"], provenance["provider"])
        if provenance["basis"] != "inferred" and pair in accepted_sources:
            accepted.append(assertion)
        else:
            unaccepted.append(assertion)
    return accepted, unaccepted


def _condition_assertions(
    definition: dict[str, Any],
    artifact: dict[str, Any],
    instance: dict[str, Any],
) -> list[dict[str, Any]]:
    source = artifact["facts"] if definition["level"] == "artifact" else instance["facts"]
    return [assertion for assertion in source if assertion["fact"] == definition["id"]]


def evaluate_condition(
    condition: dict[str, Any],
    *,
    definitions: dict[str, dict[str, Any]],
    artifact: dict[str, Any],
    instance: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    fact_id = condition["fact"]
    definition = definitions[fact_id]
    assertions = _condition_assertions(definition, artifact, instance)
    accepted, unaccepted = _accepted_assertions(definition, assertions)
    trace: dict[str, Any] = {
        "fact": fact_id,
        "outcome": "UNKNOWN",
        "accepted_assertion_ids": sorted(item["id"] for item in accepted),
        "unaccepted_assertion_ids": sorted(item["id"] for item in unaccepted),
        "assertions": [
            {
                "id": assertion["id"],
                "accepted": assertion in accepted,
                "basis": assertion["provenance"]["basis"],
                "provider": assertion["provenance"]["provider"],
                "ref_sha256": canonical_hash({"ref": assertion["provenance"]["ref"]}),
            }
            for assertion in sorted(assertions, key=lambda item: item["id"])
        ],
        "value_sha256": None,
    }
    if not accepted:
        return "UNKNOWN", trace
    distinct = {_typed_value_key(assertion["value"]) for assertion in accepted}
    if len(distinct) != 1:
        trace["outcome"] = "CONFLICT"
        return "CONFLICT", trace
    actual = accepted[0]["value"]
    trace["value_sha256"] = canonical_hash({"type": definition["type"], "value": actual})
    op = condition["op"]
    if op == "equals":
        result = actual == condition["value"] and _scalar_type(actual) == _scalar_type(condition["value"])
    elif op == "not_equals":
        result = not (
            actual == condition["value"]
            and _scalar_type(actual) == _scalar_type(condition["value"])
        )
    else:
        result = _typed_value_key(actual) in {_typed_value_key(value) for value in condition["values"]}
    outcome = "TRUE" if result else "FALSE"
    trace["outcome"] = outcome
    return outcome, trace


def evaluate_applicability(
    rule: dict[str, Any],
    *,
    rule_set: dict[str, Any],
    artifact: dict[str, Any],
    instance: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    applies_when = rule.get("applies_when")
    if applies_when is None:
        return "TRUE", []
    definitions = _definition_map(rule_set)
    traces: list[dict[str, Any]] = []
    outcomes: list[str] = []
    for condition in applies_when["all"]:
        outcome, trace = evaluate_condition(
            condition,
            definitions=definitions,
            artifact=artifact,
            instance=instance,
        )
        outcomes.append(outcome)
        traces.append(trace)
    if "FALSE" in outcomes:
        return "FALSE", traces
    if "CONFLICT" in outcomes:
        return "CONFLICT", traces
    if "UNKNOWN" in outcomes:
        return "UNKNOWN", traces
    return "TRUE", traces
