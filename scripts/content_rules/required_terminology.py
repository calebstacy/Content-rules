from __future__ import annotations

from typing import Any

from .common import literal_occurrences, result_base, text_scope


def evaluate(rule: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    base = result_base(rule)
    units, reviews, surface_applies = text_scope(artifact, rule["scope"])
    if not surface_applies:
        return {**base, "status": "NOT_APPLICABLE", "message": "No artifact instance matched the rule surface.", "evidence": [], "review_evidence": []}
    failures: list[dict[str, Any]] = []
    params = rule["params"]
    for unit in units:
        for deprecated in params["instead_of"]:
            count, capped = literal_occurrences(
                unit["text"],
                deprecated,
                case_sensitive=params["case_sensitive"],
                match=params["match"],
            )
            if count:
                evidence = {
                    "instance_id": unit["instance_id"],
                    "surface": unit["surface"],
                    "field": unit["field"],
                    "deprecated": deprecated,
                    "preferred": params["preferred"],
                    "occurrences": count,
                    "match": params["match"],
                }
                if capped:
                    evidence["occurrences_capped"] = True
                failures.append(evidence)
    if failures:
        return {**base, "status": "FAIL", "message": "Configured deprecated terminology was found.", "evidence": failures, "review_evidence": reviews}
    if reviews:
        return {**base, "status": "REVIEW", "message": "The configured scope was missing or was not text.", "evidence": [], "review_evidence": reviews}
    return {
        **base,
        "status": "PASS",
        "message": "No configured deprecated terminology was found.",
        "evidence": [],
        "review_evidence": [],
    }
