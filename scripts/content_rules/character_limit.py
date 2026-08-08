from __future__ import annotations

import unicodedata
from typing import Any

from .common import result_base, text_scope


def evaluate(rule: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    base = result_base(rule)
    units, reviews, surface_applies = text_scope(artifact, rule["scope"])
    if not surface_applies:
        return {**base, "status": "NOT_APPLICABLE", "message": "No artifact instance matched the rule surface.", "evidence": [], "review_evidence": []}
    failures: list[dict[str, Any]] = []
    maximum = rule["params"]["maximum"]
    for unit in units:
        measured = len(unicodedata.normalize("NFC", unit["text"]))
        if measured > maximum:
            failures.append(
                {
                    "instance_id": unit["instance_id"],
                    "surface": unit["surface"],
                    "field": unit["field"],
                    "measured": measured,
                    "maximum": maximum,
                    "unit": "unicode_code_points_after_nfc",
                }
            )
    if failures:
        return {**base, "status": "FAIL", "message": "One or more fields exceeded the character limit.", "evidence": failures, "review_evidence": reviews}
    if reviews:
        return {**base, "status": "REVIEW", "message": "The configured scope was missing or was not text.", "evidence": [], "review_evidence": reviews}
    return {
        **base,
        "status": "PASS",
        "message": "All applicable fields were within the character limit.",
        "evidence": [],
        "review_evidence": [],
    }
