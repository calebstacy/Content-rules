from __future__ import annotations

from typing import Any

from .common import matching_instances, result_base


def evaluate(rule: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    base = result_base(rule)
    instances = matching_instances(artifact, rule["scope"]["surfaces"])
    if not instances:
        return {**base, "status": "NOT_APPLICABLE", "message": "No artifact instance matched the rule surface.", "evidence": [], "review_evidence": []}
    failures: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    required = rule["params"]["fields"]
    require_non_empty = rule["params"]["require_non_empty"]
    for instance in instances:
        missing = [field for field in required if field not in instance["fields"]]
        empty: list[str] = []
        non_string: list[str] = []
        for field in required:
            if field not in instance["fields"]:
                continue
            value = instance["fields"][field]
            if not isinstance(value, str):
                if value is None and require_non_empty:
                    empty.append(field)
                else:
                    non_string.append(field)
            elif require_non_empty and not value.strip():
                empty.append(field)
        if missing or empty:
            failures.append(
                {
                    "instance_id": instance["id"],
                    "surface": instance["surface"],
                    "missing_fields": missing,
                    "empty_fields": empty,
                }
            )
        if non_string:
            reviews.append(
                {
                    "instance_id": instance["id"],
                    "surface": instance["surface"],
                    "non_string_fields": non_string,
                    "reason": "field_value_is_not_text",
                }
            )
    if failures:
        return {**base, "status": "FAIL", "message": "Required fields were missing or empty.", "evidence": failures, "review_evidence": reviews}
    if reviews:
        return {**base, "status": "REVIEW", "message": "Required fields were present but were not text.", "evidence": [], "review_evidence": reviews}
    return {**base, "status": "PASS", "message": "Every matching instance contains the required fields.", "evidence": [], "review_evidence": []}
